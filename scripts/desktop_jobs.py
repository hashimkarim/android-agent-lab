#!/usr/bin/env python3
"""Bounded desktop jobs. The parent owns and cancels this process group."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time

import workspace as ws
import project_config
from lab import coord


def run(command, *, cwd=None, timeout=900, env=None):
    result = subprocess.run(command, cwd=cwd, env=env, timeout=timeout)
    if result.returncode:
        raise ValueError(f'Command failed (exit {result.returncode}). See the job output.')


def emulator(identifier, operation, token=None):
    if operation not in ('start', 'stop', 'delete'):
        raise ValueError('Unknown emulator operation.')
    with ws.inventory() as data:
        row = dict(ws.item(data, 'emulators', identifier))
    serial = f"127.0.0.1:{row['adbPort']}"
    root = Path(row['root'])
    command = ['docker', 'compose', '--project-name', row['project'], '--project-directory', str(root)]
    env = {k: v for k, v in os.environ.items() if k not in ('ADB_PORT', 'WEB_PORT', 'VNC_PASSWORD', 'COMPOSE_PROJECT_NAME', 'COMPOSE_FILE')}
    with coord.locked(serial) as path:
        record = coord.read_record(path)
        if record:
            coord.check_owner(record, token, allow_expired=True)
        if operation == 'start':
            print(f"Starting {row['name']} ({serial}). First setup downloads several GB.", flush=True)
            run([*command, 'up', '-d', '--build'], env=env)
            deadline = time.monotonic() + 600
            print('Waiting for Android to boot…', flush=True)
            while time.monotonic() < deadline:
                try:
                    ws.connect(serial)
                    if ws.adb('-s', serial, 'shell', 'getprop', 'sys.boot_completed', timeout=10) == '1':
                        return {'message': f"{row['name']} is ready.", 'serial': serial}
                except (coord.CoordinationError, subprocess.TimeoutExpired):
                    pass
                time.sleep(2)
            raise ValueError('Android did not finish booting. Inspect the startup log, or stop and start it again.')
        print(f"{'Deleting' if operation == 'delete' else 'Stopping'} {row['name']}…", flush=True)
        if operation == 'delete' and record and record.get('reserved'):
            raise ValueError('Unlock the emulator before deleting it.')
        run([*command, 'down', *(['--volumes'] if operation == 'delete' else [])], timeout=120, env=env)
        if operation == 'delete':
            with ws.inventory() as data:
                data['emulators'].remove(ws.item(data, 'emulators', identifier))
                data['names'].pop(serial, None)
            if identifier != 'legacy' and root.resolve().is_relative_to(ws.home() / 'emulators'):
                shutil.rmtree(root)
            if record:
                path.unlink()
        return {'message': f"{row['name']} {'deleted with its Android data' if operation == 'delete' else 'stopped; Android data kept'}."}


def device(serial, token, args, timeout=120):
    result = coord.run_adb(serial, token, args, timeout=timeout, capture=True, actor='human:desktop')
    output = (result.stdout + result.stderr).decode(errors='replace')
    print(output, flush=True)
    if result.returncode:
        raise ValueError('Device operation failed. See the output above.')
    return output


def install(row, serial, token):
    device(serial, token, ['install', '-r', row['path']], timeout=180)
    return {'message': f"Installed {row['name']} on {serial}."}


def project_settings(row):
    values = {**row, **{key: '' for key in row.get('auto', [])}}
    config = project_config.inspect(Path(row['path']), values)
    return {**row, 'task': config['task'], 'package': row.get('package') if row.get('package') and 'package' not in row.get('auto', []) else config['package']}, config


def update_project(row, config):
    with ws.inventory() as saved:
        current = next((p for p in saved['projects'] if p['id'] == row['id']), None)
        if current:
            for key in ('task', 'package'):
                if key in current.get('auto', []) or not current.get(key):
                    current[key] = config[key]


def choose_install_output(artifacts, serial, token):
    if len(artifacts) == 1:
        return artifacts[0]
    # ABI-specific standalone APKs are safe to choose only within one app/variant.
    identities = {(a.get('module'), a.get('variant'), a.get('package')) for a in artifacts}
    if len(identities) == 1 and all(a.get('package') and a.get('variant') and all(
            f.get('filterType') == 'ABI' for f in a.get('filters', [])) for a in artifacts):
        abis = device(serial, token, ['shell', 'getprop', 'ro.product.cpu.abilist'], timeout=15).strip().split(',')
        for abi in [*abis, None]:
            matches = [a for a in artifacts if [f.get('value') for f in a.get('filters', [])] == ([abi] if abi else [])]
            if len(matches) == 1:
                return matches[0]
    raise ValueError('More than one APK was found. Choose a variant/output in project settings or the APK picker before installing.')


def fallback_outputs(row):
    """Without AGP metadata, limit conventional output paths to the requested task."""
    match = re.fullmatch(r'(.*:)?assemble([A-Z]\w*)', row['task'])
    outputs = ws.project_outputs(row)
    if not match:
        return outputs
    modules, _settings, _catalog = project_config.modules(Path(row['path']))
    module = next((m for m in modules if m['module'] == (match[1] or '').rstrip(':')), None)
    variant = match[2].lower()
    result = []
    for output in outputs:
        prefix, marker, suffix = output['path'].partition('build/outputs/apk/')
        actual = ''.join(Path(suffix).parts[:-1]).lower()
        if marker and (not module or prefix.rstrip('/') == module['directory']) and (
                actual.endswith(variant) if variant in ('debug', 'release') else actual == variant):
            result.append(output)
    return result


def build(row, serial=None, token=None):
    root = Path(row['path']).resolve(strict=True)
    if not (root / 'gradlew').is_file():
        raise ValueError('The saved project no longer contains gradlew.')
    row, config = project_settings(row)
    print(f"Building {row['name']} · {row['task']}\nProject: {root}", flush=True)
    print(f"Java {config['javaVersion'] or '?'}: {config['javaHome'] or 'Not found'}\nAndroid SDK: {config['sdkHome'] or 'Not found'}", flush=True)
    env = project_config.environment(config)
    run(['sh', str(root / 'gradlew'), '--no-daemon', '--console=plain',
        *([f"-Dorg.gradle.java.home={config['javaHome']}"] if config['javaHome'] else []), row['task']], cwd=root, timeout=1800, env=env)
    config = project_config.inspect(root, {**row, 'task': row['task']})
    update_project(row, config)
    artifacts = config['outputs'] if not row['apk'] else []
    candidates = [(root / row['apk']).resolve(strict=True)] if row['apk'] else [root / a['path'] for a in artifacts] if artifacts else [root / p['path'] for p in fallback_outputs(row)]
    if not candidates:
        raise ValueError('Build finished, but no APK was found. Set the APK output path in project settings.')
    if len(candidates) > 30 or any(not p.is_relative_to(root) for p in candidates):
        raise ValueError('Choose a single APK output path inside this project.')
    chosen = choose_install_output(artifacts or [dict(path=str(p.relative_to(root))) for p in candidates], serial, token) if serial else None
    apks = [ws.save_apk(p, row['id']) for p in candidates]
    print(f"Saved {len(apks)} APK(s) to the library.", flush=True)
    return install(apks[next(i for i,p in enumerate(candidates) if str(p.relative_to(root)) == chosen['path'])], serial, token) if serial else {'message': f"Build finished. {len(apks)} APK(s) saved.", 'apks': apks}


def app_action(row, operation, serial, token):
    row, config = project_settings(row)
    update_project(row, config)
    package = row.get('package')
    if not package:
        raise ValueError('Set the application ID in project settings first.')
    if operation == 'logcat':
        pid = device(serial, token, ['shell', 'pidof', '-s', package], timeout=10).strip()
        if not pid.isdigit():
            raise ValueError('Launch the app before requesting its logs.')
        device(serial, token, ['logcat', '-d', '-t', '500', f'--pid={pid}'], timeout=15)
        return {'message': 'App log snapshot captured.'}
    output = device(serial, token, ['shell', 'cmd', 'package', 'resolve-activity', '--brief',
        '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', package], timeout=15)
    component = next((line.strip() for line in reversed(output.splitlines()) if '/' in line and ' ' not in line), None)
    if not component or not component.startswith(package + '/') or not re.fullmatch(r'[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+', component):
        raise ValueError('No launchable activity found. Install this app on the selected device first.')
    device(serial, token, ['shell', 'am', 'start', *(['-D'] if operation == 'debug' else []), '-n', component], timeout=15)
    return {'message': 'App is waiting for a Java/Kotlin debugger. Attach from Android Studio or your debugger on this ADB host.' if operation == 'debug' else 'App launched.'}


def dispatch(data):
    action = data['action']
    token, serial = os.environ.get('ADB_COORD_TOKEN'), data.get('serial')
    if action == 'emulator':
        return emulator(data['id'], data['operation'], token)
    if action == 'importApk':
        return {'apk': ws.save_apk(data['path']), 'message': 'APK copied into your library.'}
    with ws.inventory() as saved:
        row = dict(ws.item(saved, 'apks' if action == 'install' else 'projects', data['id']))
    if action == 'install':
        return install(row, serial, token)
    if action == 'installOutput':
        output = next((p for p in ws.project_outputs(row) if p['path'] == data.get('output')), None)
        if output is None:
            raise ValueError('This APK output is no longer available. Refresh the picker.')
        apk = ws.save_apk(Path(row['path']) / output['path'], row['id'])
        return install(apk, serial, token)
    if action in ('build', 'buildInstall'):
        return build(row, serial if action == 'buildInstall' else None, token)
    if action in ('launch', 'debug', 'logcat'):
        return app_action(row, action, serial, token)
    raise ValueError('Unknown job.')


if __name__ == '__main__':
    try:
        print('@@result ' + json.dumps(dispatch(json.loads(sys.stdin.buffer.read(16385)))), flush=True)
    except (ValueError, OSError, coord.CoordinationError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr, flush=True)
        raise SystemExit(2)
