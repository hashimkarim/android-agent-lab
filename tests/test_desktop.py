"""Desktop packaging must preserve shared ownership and use writable app data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import desktop_rpc
import video
import test_coordination as fixtures


class DesktopTests(unittest.TestCase):
    setUp = fixtures.CoordinationTests.setUp
    claim = fixtures.CoordinationTests.claim

    def test_packaged_node_is_selected_only_for_the_video_child(self):
        with patch.dict(os.environ, {'ADB_VIDEO_NODE':'/opt/Android Agent Lab/android-agent-lab', 'ADB_VIDEO_ELECTRON_NODE':'1'}):
            command, env = video.node_launch({'serial':'test'})
            self.assertEqual(command[0], '/opt/Android Agent Lab/android-agent-lab')
            self.assertEqual(env['ELECTRON_RUN_AS_NODE'], '1')
            self.assertEqual(json.loads(env['ADB_VIDEO_CONFIG']), {'serial':'test'})

    def test_desktop_claim_join_and_release_cannot_override_another_thread(self):
        record = self.claim()
        with self.assertRaises(video.coord.CoordinationError):
            desktop_rpc.dispatch({'action':'claim', 'serial':record['serial'], 'owner':'human:desktop', 'reclaim':True})
        public = desktop_rpc.dispatch({'action':'check', 'serial':record['serial'], 'token':record['token']})
        self.assertNotIn('token', public)
        new = video.coord.change_claim(record['serial'], record['token'], 'handoff', 'claude:next')
        video.release_owned(record['serial'], record['token'])
        self.assertEqual(video.coord.read_record(video.coord.record_path(record['serial']))['token'], new['token'])
        video.release_owned(record['serial'], new['token'])
        self.assertIsNone(video.coord.read_record(video.coord.record_path(record['serial'])))

    def test_packaged_lab_writes_config_outside_the_read_only_runtime(self):
        destination = self.root / 'app data'
        destination.mkdir()
        script = "import lab; lab.initialize(); print(lab.ROOT); print(lab.coord.__file__)"
        result = subprocess.run([sys.executable, '-c', script], env={**os.environ,
            'PYTHONPATH':str(Path(desktop_rpc.__file__).parent), 'ADB_LAB_HOME':str(destination)},
            capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.splitlines()[0], str(destination))
        self.assertTrue((destination / '.env').is_file())
        self.assertIn('skills/adb-coordination/scripts/adb_coord.py', result.stdout)
        self.assertEqual((destination / '.env').stat().st_mode & 0o777, 0o600)
