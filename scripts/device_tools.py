#!/usr/bin/env python3
"""Bounded developer tools requested explicitly from the device toolbar."""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/adb-coordination/scripts'))
import adb_coord as coord


def command(data):
    tool = data.get('tool')
    if tool == 'logcat':
        return ['logcat', '-d', '-t', '500', '-v', 'threadtime'], 15
    if tool == 'hierarchy':
        path = '/data/local/tmp/android-agent-lab-' + secrets.token_hex(8) + '.xml'
        return ['exec-out', 'sh', '-c', f"trap 'rm -f {path}' EXIT; uiautomator dump {path} >/dev/null && cat {path}"], 25
    if tool == 'rotate':
        if type(data.get('rotation')) is not int or data['rotation'] not in (0, 1):
            raise ValueError('Invalid rotation')
        return ['shell', 'wm', 'user-rotation', 'lock', str(data['rotation'])], 15
    if tool == 'auto-rotate':
        return ['shell', 'wm', 'user-rotation', 'free'], 15
    if tool in {'settings', 'developer-options', 'app-settings'}:
        action = {'settings':'android.settings.SETTINGS', 'developer-options':'android.settings.APPLICATION_DEVELOPMENT_SETTINGS',
                  'app-settings':'android.settings.MANAGE_APPLICATIONS_SETTINGS'}[tool]
        return ['shell', 'am', 'start', '-a', action], 15
    if tool == 'install':
        # This path is provided by the local bridge after streaming a browser upload.
        path = Path(data['path'])
        if not path.is_absolute() or not path.is_file() or path.suffix != '.apk':
            raise ValueError('Invalid APK upload')
        return ['install', '-r', str(path)], 180
    raise ValueError('Unknown developer tool')


def main():
    try:
        config = json.loads(os.environ['ADB_VIDEO_CONFIG'])
        if not config['control']:
            raise coord.CoordinationError('This viewer is read-only')
        data = json.loads(sys.stdin.buffer.read(16385))
        if data.get('tool') == 'screenshot':
            result = {'image':base64.b64encode(coord.screenshot(config['serial'], config['token'])).decode()}
        else:
            args, timeout = command(data)
            completed = coord.run_adb(config['serial'], config['token'], args, timeout=timeout, capture=True)
            if completed.returncode:
                raise coord.CoordinationError(completed.stderr.decode(errors='replace')[-4000:] or completed.stdout.decode(errors='replace')[-4000:] or 'Device tool failed')
            result = {'text':completed.stdout.decode(errors='replace')[-512000:]}
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, coord.CoordinationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
