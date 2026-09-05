#!/usr/bin/env python3
"""Small JSON interface for the desktop launcher. Never executes shell strings."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import lab

coord = lab.coord


def dispatch(data):
    action = data['action']
    if action == 'status':
        result = {'python': platform.python_version(), 'devices': [],
                  'docker': bool(shutil.which('docker')), 'kvm': os.access('/dev/kvm', os.R_OK | os.W_OK),
                  'architecture': platform.machine(), 'server': coord.server_id()}
        try:
            binary = coord.adb_binary()
            result['adb'] = binary
            listing = subprocess.run([binary, '-L', coord.server_id(), 'devices', '-l'],
                                     capture_output=True, text=True, timeout=15, check=True)
            for line in listing.stdout.splitlines():
                fields = line.split()
                if len(fields) < 2 or line.startswith(('List of devices', '*')):
                    continue
                serial, state = fields[:2]
                details = dict(f.split(':', 1) for f in fields[2:] if ':' in f)
                record = coord.read_record(coord.record_path(serial))
                result['devices'].append({'serial': serial, 'state': state,
                                          'model': details.get('model', serial).replace('_', ' '),
                                          'claim': coord.public_record(record) if record else None})
        except (OSError, coord.CoordinationError, subprocess.SubprocessError) as exc:
            result['error'] = str(exc)
        return result
    if action == 'claim':
        return coord.claim(data['serial'], data['owner'], str(lab.ROOT), ttl=3600,
                           note='Shared desktop and browser session', reclaim=data.get('reclaim', False))
    if action == 'check':
        with coord.locked(data['serial']) as path:
            record = coord.read_record(path)
            coord.check_owner(record, data['token'])
            return coord.public_record(record)
    if action == 'release':
        return coord.change_claim(data['serial'], data['token'], 'release')
    raise ValueError('Unknown desktop operation')


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 or newer is required.')
    try:
        data = json.loads(sys.stdin.buffer.read(16385))
        print(json.dumps(dispatch(data)))
    except (KeyError, TypeError, ValueError, OSError, coord.CoordinationError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
