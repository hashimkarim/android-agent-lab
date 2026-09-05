"""Launcher behavior without Docker or a real Android device."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lab


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_init_preserves_existing_credentials_and_custom_ports(self):
        self.assertTrue(lab.initialize(self.root))
        initial = (self.root / ".env").read_text()
        self.assertEqual(len(lab.config(self.root)["VNC_PASSWORD"]), 8)
        self.assertFalse(lab.initialize(self.root))
        self.assertEqual((self.root / ".env").read_text(), initial)
        (self.root / ".env").write_text("WEB_PORT=8888\nADB_PORT=16666\nVNC_PASSWORD=abcd1234\n")
        settings = lab.config(self.root)
        self.assertEqual(lab.device_serial(settings), "127.0.0.1:16666")
        self.assertIn(":8888/", lab.preview_url(settings))

    def test_shell_overrides_match_compose_and_password_is_opt_in(self):
        with patch.dict(os.environ, {"WEB_PORT": "9999", "VNC_PASSWORD": "aB12345z"}):
            settings = lab.config(self.root)
        self.assertNotIn("aB12345z", lab.preview_url(settings))
        query = parse_qs(urlparse(lab.preview_url(settings, password=True)).query)
        self.assertEqual(query["password"], ["aB12345z"])
        self.assertIn(":9999/", lab.preview_url(settings))

    def test_ambiguous_ports_and_unrepresentable_passwords_fail(self):
        for text in ["WEB_PORT=22", "WEB_PORT=65536", "WEB_PORT=008765",
                     "ADB_PORT=8765", "WEB_PORT=abc", "VNC_PASSWORD=123456789",
                     "VNC_PASSWORD=$PASSWORD", "VNC_PASSWORD=é"]:
            with self.subTest(text=text):
                (self.root / ".env").write_text(text)
                with self.assertRaises(ValueError):
                    lab.config(self.root)

    def test_container_changes_require_live_owners_token(self):
        record = {"expires_at": time.time() + 100, "owner": "claude:other", "token": "secret"}
        for token in [None, "wrong"]:
            with self.assertRaises(lab.coord.CoordinationError):
                lab.require_no_other_owner(record, token)
        lab.require_no_other_owner(record, "secret")
        lab.require_no_other_owner(None)
        lab.require_no_other_owner({**record, "expires_at": 0})

    def test_ready_requires_android_property_not_a_container_or_adb_port(self):
        responses = [subprocess.CompletedProcess([], 0, b"\r\n"),
                     subprocess.CompletedProcess([], 1, b"1\n"),
                     subprocess.CompletedProcess([], 0, b"1\r\n")]
        with patch.object(lab, "connect"), patch.object(lab.subprocess, "run", side_effect=responses) as run, \
             patch.object(lab.time, "sleep"), patch.object(lab.coord, "adb_binary", return_value="fake-adb"):
            lab.wait_ready("127.0.0.1:15555", 5)
        self.assertEqual(run.call_count, 3)
        self.assertIn("sys.boot_completed", run.call_args.args[0])
        self.assertIn("127.0.0.1:15555", run.call_args.args[0])

    def test_connection_failure_is_reported_even_if_adb_exits_zero(self):
        with patch.object(lab.coord, "adb_binary", return_value="fake-adb"), \
             patch.object(lab.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "failed to connect", "")):
            with self.assertRaises(lab.coord.CoordinationError):
                lab.connect("127.0.0.1:15555")

    def test_down_with_busy_claim_does_not_touch_docker(self):
        with patch.dict(os.environ, {"ADB_COORD_STATE": str(self.root / "state")}):
            record = lab.coord.claim("127.0.0.1:15555", "claude:other", str(self.root))
            with patch.object(lab, "config", return_value={"WEB_PORT": "8765", "ADB_PORT": "15555"}), \
                 patch.object(lab, "compose") as compose, patch.object(sys, "argv", ["lab.py", "down"]), \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(lab.main(), 2)
                compose.assert_not_called()
            lab.coord.change_claim(record["serial"], record["token"], "release")


if __name__ == "__main__":
    unittest.main()
