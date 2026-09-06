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
import workspace as ws

coord = lab.coord


def dispatch(data):
    action = data['action']
    if action == 'status':
        result = {'python': platform.python_version(), 'devices': [],
                  'docker': bool(shutil.which('docker')), 'kvm': os.access('/dev/kvm', os.R_OK | os.W_OK),
                  'architecture': platform.machine(), 'server': coord.server_id()}
        with ws.inventory() as saved:
            result.update(ws.public_inventory(saved))
        ws.emulator_states(result['emulators'])
        try:
            binary = coord.adb_binary()
            result['adb'] = binary
            listing = subprocess.run([binary, '-L', coord.server_id(), 'devices', '-l'],
                                     capture_output=True, text=True, timeout=15, check=True)
            result['devices'] = ws.devices(listing.stdout, saved)
        except (OSError, coord.CoordinationError, subprocess.SubprocessError) as exc:
            result['error'] = str(exc)
            result['devices'] = ws.devices('', saved)
        return result
    if action == 'discover':
        return ws.discover()
    if action == 'networks':
        return ws.networks()
    if action == 'pair':
        return ws.pair(data['address'], data['code'])
    if action == 'connect':
        return ws.connect(data['address'])
    if action == 'createEmulator':
        return ws.create_emulator(data['name'])
    if action == 'rename':
        return ws.rename(data['kind'], data['id'], data['name'])
    if action == 'saveProject':
        return ws.save_project(data)
    if action == 'openProject':
        return ws.open_project(data['path'])
    if action == 'inspectProject':
        import project_config
        return project_config.inspect(ws.project_root(data['path']), data)
    if action == 'library':
        return ws.library()
    if action == 'forget':
        return ws.forget(data['kind'], data['id'])
    if action == 'reservation':
        return ws.reservation(data['serial'], data['enabled'], data.get('token'), data.get('reclaim') is True)
    if action == 'reservationToken':
        return {'token': ws.reservation_token(data['serial'])}
    if action == 'claim':
        return coord.claim(data['serial'], data['owner'], str(lab.ROOT), ttl=3600,
                           note='Shared desktop and browser session', reclaim=data.get('reclaim', False))
    if action == 'checkSession':
        # Claim records are replaced atomically. Reading job progress must not
        # compete with the running install's operation lock or renew ownership.
        record = coord.read_record(coord.record_path(data['serial']))
        coord.check_owner(record, data['token'])
        return coord.public_record(record)
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
