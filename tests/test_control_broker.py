"""Live scrcpy gestures must exclude cooperating ADB operations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from control_broker import Broker
import device_tools
import adb_coord as coord
import test_coordination as fixtures


class ControlBrokerTests(unittest.TestCase):
    setUp=fixtures.CoordinationTests.setUp
    claim=fixtures.CoordinationTests.claim

    def test_lock_covers_gesture_and_activity_omits_private_data(self):
        record=self.claim();broker=Broker(record)
        event={'id':'gesture','actor':'human:test','kind':'pointer','points':[10,20],'text':'secret'}
        broker.acquire(event)
        try:
            with self.assertRaisesRegex(coord.CoordinationError,'operation in progress'):
                coord.run_adb(record['serial'],record['token'],['get-state'])
            with self.assertRaises(coord.CoordinationError):
                coord.change_claim(record['serial'],record['token'],'handoff','other')
        finally:broker.release({**event,'points':[30,40]})
        coord.run_adb(record['serial'],record['token'],['get-state'],capture=True)
        state=json.loads(coord.record_path(record['serial']).with_suffix('.activity').read_text())
        self.assertNotIn('secret',json.dumps(state));self.assertEqual(state['events'][-1]['points'],[30,40])

    def test_eof_releases_lock_and_wrong_token_never_acquires(self):
        record=self.claim()
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/control_broker.py')],
            env={**os.environ,'ADB_VIDEO_CONFIG':json.dumps({**record,'control':True})},stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        child.stdin.write(json.dumps({'id':1,'action':'acquire','event':{'id':'test','actor':'codex:test','kind':'key'}})+'\n');child.stdin.flush()
        self.assertTrue(json.loads(child.stdout.readline())['ok'])
        child.stdin.close();child.wait(timeout=3);child.stdout.close()
        coord.run_adb(record['serial'],record['token'],['get-state'],capture=True)
        broker=Broker({**record,'token':'wrong'})
        with self.assertRaises(coord.CoordinationError):broker.acquire({'id':'test','actor':'codex:test','kind':'key'})
        with coord.locked(record['serial']):pass

    def test_developer_commands_are_bounded_and_not_a_general_shell_endpoint(self):
        self.assertEqual(device_tools.command({'tool':'logcat'})[0],['logcat','-d','-t','500','-v','threadtime'])
        args,timeout=device_tools.command({'tool':'hierarchy'})
        self.assertLessEqual(timeout,30);self.assertIn('trap',args[-1]);self.assertIn('rm -f',args[-1])
        self.assertEqual(device_tools.command({'tool':'rotate','rotation':1})[0],['shell','wm','user-rotation','lock','1'])
        self.assertEqual(device_tools.command({'tool':'auto-rotate'})[0],['shell','wm','user-rotation','free'])
        for data in ({'tool':'shell','command':'reboot'},{'tool':'install','path':'relative.apk'},{'tool':'clear-data'},
                     {'tool':'rotate','rotation':'1; reboot'},{'tool':'rotate','rotation':True}):
            with self.assertRaises(ValueError):device_tools.command(data)
