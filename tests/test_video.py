"""Verify video input permissions and shell-safe text without touching devices."""
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import video
import test_coordination as fixtures


class VideoTests(unittest.TestCase):
    setUp = fixtures.CoordinationTests.setUp
    claim = fixtures.CoordinationTests.claim

    def test_text_is_one_literal_android_shell_argument(self):
        text = "hello'; echo injected $(id) `id` & world"
        command = video.video_input({'kind':'text', 'text':text})
        self.assertEqual(shlex.split(' '.join(command[1:])), ['input','text',text.replace(' ', '%s')])
        for value in ['', '\n', '🙂', '%s', 'a'*501]:
            with self.assertRaises(ValueError):
                video.video_input({'kind':'text', 'text':value})

    def test_target_endpoint_is_explicit_and_validated(self):
        self.assertEqual(video.endpoint('tcp:localhost:5037'), {'host':'localhost','port':5037})
        self.assertEqual(video.endpoint('tcp:[::1]:5037'), {'host':'::1','port':5037})
        for value in ['tcp:localhost:99999', 'localfilesystem:other', 'tcp:5037']:
            with self.assertRaises(ValueError):
                video.endpoint(value)

    def run_rpc(self, record, control=True):
        settings = {'serial':record['serial'], 'token':record['token'], 'control':control}
        body = io.TextIOWrapper(io.BytesIO(b'{"kind":"tap","x":12,"y":24}'))
        with patch.dict(os.environ, {'ADB_VIDEO_CONFIG':json.dumps(settings)}), patch.object(sys, 'stdin', body), patch.object(sys, 'stdout', io.StringIO()):
            video.rpc()

    def test_video_input_rechecks_handoff_and_read_only(self):
        record = self.claim()
        with self.assertRaises(video.coord.CoordinationError):
            self.run_rpc(record, control=False)
        self.assertFalse((self.root/'argv').exists())
        self.run_rpc(record)
        self.assertEqual(json.loads((self.root/'argv').read_text())[-5:], ['shell','input','tap','12','24'])
        (self.root/'argv').unlink()
        video.coord.change_claim(record['serial'], record['token'], 'handoff', 'claude:next')
        with self.assertRaises(video.coord.CoordinationError):
            self.run_rpc(record)
        self.assertFalse((self.root/'argv').exists())

    def test_server_binary_must_match_the_pinned_digest(self):
        file = self.root/'server.jar'
        file.write_bytes(b'wrong server')
        with self.assertRaises(video.coord.CoordinationError):
            video.verify_server(file)

    def test_display_query_supports_watch_sizes_and_prefers_android_override(self):
        for output, expected in [('Physical size: 450x450', (450, 450)),
                                 ('Physical size: 1080x2400\nOverride size: 720x1600', (720, 1600))]:
            with patch.object(video.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, 'device\n', ''),
                    subprocess.CompletedProcess([], 0, output, '')]) as run:
                self.assertEqual(video.display_size('192.168.1.159:43443'), expected)
                self.assertEqual(run.call_args.args[0][-5:], ['-s', '192.168.1.159:43443', 'shell', 'wm', 'size'])

    def test_offline_and_slow_watch_have_actionable_errors_before_scrcpy_start(self):
        with patch.object(video.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'error: device offline')) as run:
            with self.assertRaisesRegex(video.coord.CoordinationError, 'device offline.*Update connection'):
                video.display_size('192.168.44.96:34651')
            self.assertEqual(run.call_count, 1)
        with patch.object(video.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, 'device\n', ''), subprocess.TimeoutExpired('adb', 10)]):
            with self.assertRaisesRegex(video.coord.CoordinationError, 'current IP and connection port'):
                video.display_size('192.168.44.96:34651')
