#!/usr/bin/env python3
"""Isolated behavioral tests; never connect to real ADB devices."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/adb-coordination/scripts"))
import adb_coord as coord


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / "fake-adb"
        self.fake.write_text("""#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
Path(os.environ['FAKE_LOG']).write_text(json.dumps(sys.argv[1:]))
time.sleep(float(os.environ.get('FAKE_DELAY','0')))
if sys.argv[-3:] == ['exec-out','screencap','-p']:
 import base64
 sys.stdout.buffer.write(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=='))
else:
 print('device')
sys.exit(int(os.environ.get('FAKE_EXIT','0')))
""")
        self.fake.chmod(0o700)
        self.env = patch.dict(os.environ, {"ADB_COORD_STATE": str(self.root / "state"),
                             "ADB_COORD_ADB": str(self.fake), "FAKE_LOG": str(self.root / "argv"),
                             "ADB_SERVER_SOCKET": "tcp:localhost:5037"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def claim(self, serial="emulator-5580", ttl=1800):
        return coord.claim(serial, "codex:one", str(self.root), ttl)

    def test_competing_processes_have_one_owner(self):
        command = [sys.executable, str(Path(coord.__file__)), "claim", "--serial", "emulator-5580", "--owner"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda i: subprocess.run(command + [f"thread:{i}"], capture_output=True), range(8)))
        self.assertEqual(sum(r.returncode == 0 for r in results), 1)
        self.assertEqual(sum(r.returncode == 2 for r in results), 7)

    def test_handoff_rotates_token_and_rejects_previous_owner(self):
        old = self.claim()
        new = coord.change_claim(old["serial"], old["token"], "handoff", "claude:two", "Next: checkout")
        self.assertNotEqual(old["token"], new["token"])
        self.assertEqual(new["note"], "Next: checkout")
        with self.assertRaises(coord.CoordinationError):
            coord.run_adb(old["serial"], old["token"], ["get-state"])
        with self.assertRaises(coord.CoordinationError):
            coord.change_claim(old["serial"], old["token"], "release")
        self.assertEqual(coord.run_adb(new["serial"], new["token"], ["get-state"], capture=True).returncode, 0)

    def test_expired_recovery_is_explicit(self):
        old = self.claim()
        old["expires_at"] = time.time() - 1
        coord.save_record(coord.record_path(old["serial"]), old)
        with self.assertRaises(coord.CoordinationError):
            self.claim()
        new = coord.claim(old["serial"], "t3:two", str(self.root), reclaim=True)
        with self.assertRaises(coord.CoordinationError):
            coord.change_claim(old["serial"], old["token"], "renew")
        self.assertNotEqual(old["token"], new["token"])

    def test_live_operation_blocks_expired_takeover_but_other_devices_work(self):
        old = self.claim(ttl=1)
        command = [sys.executable, str(Path(coord.__file__)), "run", "--serial", old["serial"],
                   "--token", old["token"], "--", "get-state"]
        process = subprocess.Popen(command, env={**os.environ, "FAKE_DELAY": "2"}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "argv").exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.root / "argv").exists())
            time.sleep(1.1)
            with self.assertRaisesRegex(coord.CoordinationError, "operation in progress"):
                coord.claim(old["serial"], "t3:two", str(self.root), reclaim=True)
            self.claim("emulator-5582")
            process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0)
            current = coord.read_record(coord.record_path(old["serial"]))
            self.assertGreater(current["expires_at"], time.time())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_target_and_exit_code_preserved(self):
        old = self.claim()
        with patch.dict(os.environ, {"FAKE_EXIT": "7"}):
            result = coord.run_adb(old["serial"], old["token"], ["shell", "echo", "a b;$x"], capture=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(json.loads((self.root / "argv").read_text()),
                         ["-L", "tcp:localhost:5037", "-s", old["serial"], "shell", "echo", "a b;$x"])
        with self.assertRaises(coord.CoordinationError):
            coord.run_adb(old["serial"], old["token"], ["kill-server"])
        with self.assertRaises(coord.CoordinationError):
            coord.run_adb(old["serial"], old["token"], ["-s", "other", "shell", "true"])

    def test_timeout_releases_operation_lock(self):
        old = self.claim()
        with patch.dict(os.environ, {"FAKE_DELAY": "3"}):
            with self.assertRaises(subprocess.TimeoutExpired):
                coord.run_adb(old["serial"], old["token"], ["get-state"], timeout=.1, capture=True)
        coord.change_claim(old["serial"], old["token"], "release")
        self.claim()

    def test_passive_screenshot_does_not_extend_lease_and_status_hides_token(self):
        old = self.claim()
        self.assertTrue(coord.screenshot(old["serial"], old["token"]).startswith(b"\x89PNG"))
        self.assertEqual(coord.read_record(coord.record_path(old["serial"]))["expires_at"], old["expires_at"])
        self.assertNotIn("token", coord.public_record(old))

    def test_wrong_endpoint_and_bad_ttl_rejected(self):
        old = self.claim()
        with patch.dict(os.environ, {"ADB_SERVER_SOCKET": "tcp:localhost:5038"}):
            with self.assertRaises(coord.CoordinationError):
                coord.run_adb(old["serial"], old["token"], ["get-state"])
        for ttl in [0, -1, float("nan"), float("inf"), 86401]:
            with self.assertRaises(coord.CoordinationError):
                coord.claim("other", "x", str(self.root), ttl)


if __name__ == "__main__":
    unittest.main()
