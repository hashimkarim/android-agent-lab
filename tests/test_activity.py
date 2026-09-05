"""Cursor feedback follows actual, authorized input and excludes typed content."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import stat
import time
import unittest
from unittest.mock import patch
import test_coordination as fixtures
import adb_coord as coord


class ActivityTests(unittest.TestCase):
    setUp = fixtures.CoordinationTests.setUp
    claim = fixtures.CoordinationTests.claim

    def events(self, record):
        return json.loads(coord.record_path(record['serial']).with_suffix('.activity').read_text())

    def test_pointer_is_announced_during_input_and_records_failure(self):
        record = self.claim()
        gate = self.root/'finish-input'
        with patch.dict(os.environ, {'FAKE_GATE':str(gate), 'FAKE_EXIT':'7'}), ThreadPoolExecutor() as pool:
            future = pool.submit(coord.run_adb, record['serial'], record['token'], ['shell','input','swipe','10','20','80','90','300'], capture=True)
            try:
                deadline = time.monotonic()+3
                while not (self.root/'argv').exists() and time.monotonic()<deadline:
                    time.sleep(.01)
                event = self.events(record)['events'][-1]
                self.assertEqual(event['phase'], 'start')
                self.assertEqual(event['points'], [10,20,80,90])
                self.assertEqual(event['actor'], 'codex:one')
            finally:
                gate.touch()
            self.assertEqual(future.result(timeout=3).returncode, 7)
        events = self.events(record)['events']
        self.assertEqual(events[-1]['id'], events[0]['id'])
        self.assertFalse(events[-1]['ok'])
        self.assertEqual(events[-1]['phase'], 'complete')

    def test_feedback_is_private_bounded_and_reset_on_handoff(self):
        record = self.claim()
        secret = 'private-password-not-for-viewers'
        for i in range(18):
            coord.run_adb(record['serial'], record['token'], ['shell','input','text',secret], actor='claude:two', capture=True)
        state = self.events(record)
        self.assertEqual(len(state['events']), 32)
        self.assertNotIn(secret, json.dumps(state))
        self.assertNotIn(record['token'], json.dumps(state))
        self.assertEqual(state['events'][-1]['actor'], 'claude:two')
        self.assertEqual(state['events'][-1]['kind'], 'typing')
        mode = coord.record_path(record['serial']).with_suffix('.activity').stat().st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o600)
        new = coord.change_claim(record['serial'], record['token'], 'handoff', owner='t3:next')
        coord.run_adb(new['serial'], new['token'], ['shell','input','tap','10','20'], capture=True)
        self.assertEqual(len(self.events(new)['events']), 2)
        self.assertNotEqual(state['session'], self.events(new)['session'])

    def test_rejected_or_non_input_commands_do_not_emit_cursors(self):
        record = self.claim()
        path = coord.record_path(record['serial']).with_suffix('.activity')
        with self.assertRaises(coord.CoordinationError):
            coord.run_adb(record['serial'], 'wrong-token', ['shell','input','tap','10','20'], capture=True)
        self.assertFalse(path.exists())
        self.assertFalse((self.root/'argv').exists())
        coord.run_adb(record['serial'], record['token'], ['get-state'], capture=True)
        self.assertFalse(path.exists())
        with patch.object(coord, 'save_record', side_effect=OSError('feedback unavailable')):
            # A feedback failure must not suppress the actual input operation.
            result = coord.run_adb(record['serial'], record['token'], ['shell','input','tap','1','2'], capture=True, renew=False)
        self.assertEqual(result.returncode, 0)

    def test_direct_shell_forms_and_safe_keyboard_descriptions(self):
        self.assertEqual(coord.input_activity(['shell','input touchscreen tap 10 20'])['points'], [10,20])
        for command in ['input tap 10 20; reboot', 'input tap nan 20', 'input tap 10 20 && input tap 30 40']:
            self.assertIsNone(coord.input_activity(['shell',command]))
        self.assertEqual(coord.input_activity(['shell','input','keyevent','KEYCODE_HOME'])['key'], 'Home')
        self.assertEqual(coord.input_activity(['shell','input','keyevent','KEYCODE_A'])['key'], 'Key input')
        record = self.claim()
        with patch.dict(os.environ, {'ADB_COORD_ACTOR':'codex:shared-session'}):
            coord.run_adb(record['serial'], record['token'], ['shell','input','tap','2','4'], capture=True)
        self.assertEqual(self.events(record)['events'][-1]['actor'], 'codex:shared-session')
        for label in ['', 'a'*81, 'name\nforged']:
            with self.assertRaises(coord.CoordinationError):
                coord.activity_actor(label)
