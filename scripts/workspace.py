"""Persistent desktop inventory and ADB discovery. No third-party Python dependencies."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import time
import uuid

import lab
from lab import coord


def home():
    root = Path(os.environ.get('ADB_LAB_WORKSPACE', str(lab.ROOT / '.workspace'))).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


@contextmanager
def inventory():
    root = home()
    with (root / 'workspace.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / 'workspace.json'
        if path.exists():
            data = json.loads(path.read_text())
            if data.get('version') != 1:
                raise ValueError('Unsupported workspace format; your data has been preserved.')
        else:
            data = dict(version=1, names={}, emulators=[], projects=[], apks=[], reservations={})
            # Adopt the previous desktop slot without moving or resetting its volumes.
            if (lab.ROOT / '.env').exists():
                settings = lab.config()
                data['emulators'].append(dict(id='legacy', name='Android 16', project='android-agent-lab',
                    root=str(lab.ROOT), adbPort=int(settings['ADB_PORT']), webPort=int(settings['WEB_PORT'])))
        before = json.dumps(data, sort_keys=True)
        yield data
        if not path.exists() or json.dumps(data, sort_keys=True) != before:
            coord.save_record(path, data)


def name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 80 or re.search(r'[\x00-\x1f\x7f]', value):
        raise ValueError('Use a name of 1–80 characters.')
    return value.strip()


def item(data, collection, identifier):
    found = next((row for row in data[collection] if row['id'] == identifier), None)
    if found is None:
        raise ValueError('This saved item no longer exists. Refresh the workspace.')
    return found


def endpoint(value):
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError('Enter an IP address and port, for example 192.168.1.20:37123.')
    match = re.fullmatch(r'(\[[^\]]+\]|[^:]+):(\d{1,5})', value.strip())
    if not match or not 1 <= int(match[2]) <= 65535:
        raise ValueError('Enter the IP address and port shown on the phone.')
    address = ipaddress.ip_address(match[1].strip('[]'))
    return f'[{address}]:{int(match[2])}' if address.version == 6 else f'{address}:{int(match[2])}'


def adb(*args, timeout=15, input=None):
    result = subprocess.run([coord.adb_binary(), '-L', coord.server_id(), *args],
        input=input, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise coord.CoordinationError(result.stderr.strip() or result.stdout.strip() or 'ADB request failed.')
    return result.stdout.strip()


def parse_services(output):
    services = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 3 or fields[1].rstrip('.') not in ('_adb-tls-pairing._tcp', '_adb-tls-connect._tcp'):
            continue
        try:
            address = endpoint(fields[2])
        except ValueError:
            continue
        services.append(dict(name=fields[0], kind='pairing' if 'pairing' in fields[1] else 'connect', address=address))
    return services


def parse_avahi(output):
    services = []
    for line in output.splitlines():
        fields = line.split(';')
        if len(fields) < 9 or fields[0] != '=' or fields[4] not in ('_adb-tls-pairing._tcp', '_adb-tls-connect._tcp'):
            continue
        try:
            host = f'[{fields[7]}]' if ':' in fields[7] else fields[7]
            address = endpoint(f'{host}:{fields[8]}')
            # Avahi's parsable output escapes bytes as three decimal digits.
            service_name = re.sub(r'\\(\d{3})', lambda match: chr(int(match[1])), fields[3])
        except (ValueError, OverflowError):
            continue
        row = dict(name=service_name, kind='pairing' if 'pairing' in fields[4] else 'connect', address=address)
        if row not in services:
            services.append(row)
    return services


def discover():
    try:
        return {'services': parse_services(adb('mdns', 'services')), 'available': True, 'backend': 'adb'}
    except (coord.CoordinationError, subprocess.SubprocessError, OSError) as error:
        adb_error = str(error)
    binary = shutil.which('avahi-browse')
    local_server = re.fullmatch(r'tcp:(?:localhost|127\.0\.0\.1|\[::1\]):\d+', coord.server_id())
    if binary and local_server:
        def browse(kind):
            try:
                # Avahi resolves missing addresses for about five seconds and
                # may buffer valid results until it exits. Let that timeout
                # finish before killing the process and losing its output.
                result = subprocess.run([binary, '--parsable', '--resolve', '--terminate', '--no-db-lookup', kind],
                    capture_output=True, text=True, timeout=8)
                services = parse_avahi(result.stdout)
                if result.returncode and not services:
                    raise ValueError(result.stderr.strip() or 'System discovery is unavailable.')
                return services
            except subprocess.TimeoutExpired as error:
                output = error.stdout or ''
                return parse_avahi(output.decode(errors='replace') if isinstance(output, bytes) else output)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(browse, ['_adb-tls-pairing._tcp', '_adb-tls-connect._tcp']))
            services = []
            for group in results:
                for row in group:
                    if row not in services:
                        services.append(row)
            return {'services': services, 'available': True, 'backend': 'avahi'}
        except (ValueError, OSError, subprocess.SubprocessError):
            pass
    message = ('Nearby discovery is unavailable. Pairing code and manual IP/port entry still work. '
               'For QR pairing, enable Avahi and install avahi-utils (Ubuntu/Debian), avahi-tools (Fedora), or avahi (Arch).')
    if not local_server:
        message = 'This ADB host has no working mDNS discovery. Use a pairing code and manual IP/port, or run discovery on the ADB host.'
    return {'services': [], 'available': False, 'message': message, 'detail': adb_error[:500]}


def networks():
    """Offer physical LAN addresses as editable pairing-field defaults."""
    try:
        addresses = json.loads(subprocess.run(['ip', '-j', '-4', 'addr', 'show', 'up'], capture_output=True, text=True, check=True, timeout=3).stdout)
        routes = json.loads(subprocess.run(['ip', '-j', '-4', 'route', 'show', 'default'], capture_output=True, text=True, check=True, timeout=3).stdout)
        preferred = next((r.get('dev') for r in sorted(routes, key=lambda r: r.get('metric', 0))), None)
        result = []
        for interface in addresses:
            identifier = interface['ifname']
            if identifier.startswith(('lo', 'docker', 'br-', 'veth', 'tailscale', 'tun', 'tap', 'wg')) or interface.get('operstate') != 'UP':
                continue
            for address in interface.get('addr_info', []):
                if address.get('family') != 'inet' or address.get('scope') != 'global':
                    continue
                ip = str(ipaddress.IPv4Address(address['local']))
                result.append(dict(address=ip, prefix=ip.rsplit('.', 1)[0] + '.', interface=identifier,
                    kind='Wi-Fi' if identifier.startswith('wl') else 'Ethernet', prefixLength=address['prefixlen'], preferred=identifier == preferred))
        return {'networks': sorted(result, key=lambda row: not row['preferred'])}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return {'networks': []}


def pair(address, code):
    address = endpoint(address)
    if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9]{6,64}', code):
        raise ValueError('Enter the six-digit pairing code shown on the phone.')
    # Pairing secrets go over stdin, never process arguments or persistent logs.
    output = adb('pair', address, input=code + '\n', timeout=30)
    if 'successfully paired' not in output.lower():
        raise coord.CoordinationError('Pairing failed. Check the pairing port and use a fresh code from the phone.')
    guid = re.search(r'\[guid=([^\]\s]{1,200})\]', output)
    return {'guid': guid[1] if guid else None, 'message': 'Phone paired. If it does not appear, enter the connection IP and port from the main Wireless debugging screen.'}


def connect(address):
    address = endpoint(address)
    try:
        output = adb('connect', address, timeout=8)
    except subprocess.TimeoutExpired as error:
        raise coord.CoordinationError(f'{address} did not respond. Wake the device and use its current IP and connection port from Wireless debugging.') from error
    if not any(text in output.lower() for text in ('connected to', 'already connected')):
        raise coord.CoordinationError(output)
    return {'message': output}


def devices(output, data):
    found = []
    for line in output.splitlines():
        if not line.strip() or line.startswith(('List of', '*')):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        serial, state = fields[:2]
        if state == 'no' and len(fields) > 2 and fields[2] == 'permissions':
            state = 'no permissions'
        props = dict(field.split(':', 1) for field in fields[2:] if ':' in field)
        record = coord.read_record(coord.record_path(serial))
        emulator = next((e for e in data['emulators'] if serial == f"127.0.0.1:{e['adbPort']}"), None)
        model = props.get('model', serial).replace('_', ' ')
        found.append(dict(serial=serial, state=state, model=model, name=data['names'].get(serial, emulator['name'] if emulator else model),
            transport='Emulator' if emulator or serial.startswith('emulator-') else 'USB' if 'usb' in props or state == 'no permissions' else 'Wi-Fi' if ':' in serial or '._tcp' in serial else 'ADB',
            claim=coord.public_record(record) if record else None, lockedHere=serial in data['reservations']))
    # Renamed devices remain visible after unplugging.
    for serial in sorted(set(data['names']) | set(data['reservations'])):
        label = data['names'].get(serial, serial)
        if not any(d['serial'] == serial for d in found):
            record = coord.read_record(coord.record_path(serial))
            found.append(dict(serial=serial, name=label, model=serial, state='disconnected', transport='Saved',
                claim=coord.public_record(record) if record else None, lockedHere=serial in data['reservations']))
    return found


def public_inventory(data):
    result = {key: data[key] for key in ('emulators', 'projects', 'apks')}
    result['emulators'] = [{**e, 'serial': f"127.0.0.1:{e['adbPort']}",
        'lockedHere': f"127.0.0.1:{e['adbPort']}" in data['reservations'],
        'claim': (coord.public_record(r) if (r := coord.read_record(coord.record_path(f"127.0.0.1:{e['adbPort']}"))) else None)} for e in data['emulators']]
    return result


def emulator_states(rows):
    if not rows or not shutil.which('docker'):
        return
    try:
        result = subprocess.run(['docker', 'ps', '-a', '--filter', 'label=com.docker.compose.service=emulator',
            '--format', '{{.Label "com.docker.compose.project"}}\t{{.State}}'], text=True, capture_output=True, timeout=5)
        states = dict(line.split('\t', 1) for line in result.stdout.splitlines() if '\t' in line)
        for row in rows:
            row['state'] = states.get(row['project'], 'stopped') if result.returncode == 0 else 'unknown'
    except (OSError, subprocess.SubprocessError):
        for row in rows:
            row['state'] = 'unknown'


def create_emulator(label):
    label = name(label)
    with inventory() as data:
        identifier = uuid.uuid4().hex[:12]
        root = home() / 'emulators' / identifier
        used = {e[key] for e in data['emulators'] for key in ('adbPort', 'webPort')}
        sockets = []
        try:
            ports = []
            for _ in range(2):
                for _ in range(100):
                    probe = socket.socket()
                    probe.bind(('127.0.0.1', 0))
                    port = probe.getsockname()[1]
                    if port not in used:
                        sockets.append(probe)
                        ports.append(port)
                        used.add(port)
                        break
                    probe.close()
                else:
                    raise ValueError('No available emulator port found.')
            root.mkdir(parents=True, mode=0o700)
            for filename in ('compose.yaml', 'Dockerfile', '.dockerignore'):
                shutil.copy2(lab.SOURCE_ROOT / filename, root / filename)
            with (root / '.env').open('x') as out:
                os.chmod(out.name, 0o600)
                out.write(f'VNC_PASSWORD={secrets.token_hex(4)}\nADB_PORT={ports[0]}\nWEB_PORT={ports[1]}\n')
            row = dict(id=identifier, name=label, project=f'aal-{identifier}', root=str(root), adbPort=ports[0], webPort=ports[1])
            data['emulators'].append(row)
            return row
        finally:
            for probe in sockets:
                probe.close()


def rename(kind, identifier, label):
    label = name(label)
    with inventory() as data:
        if kind == 'device':
            coord.record_path(identifier)
            data['names'][identifier] = label
        elif kind in ('emulators', 'apks'):
            row = item(data, kind, identifier)
            row['name'] = label
            if kind == 'emulators':
                data['names'][f"127.0.0.1:{row['adbPort']}"] = label
        else:
            raise ValueError('Unknown item type.')
    return {'ok': True}


def project_root(value):
    root = Path(value).expanduser().resolve(strict=True)
    if not root.is_dir() or not (root / 'gradlew').is_file():
        raise ValueError('Choose the Gradle project root containing gradlew.')
    return root


def open_project(value):
    """Register once per canonical root; reopening never resets build settings."""
    root = project_root(value)
    import project_config
    config = project_config.inspect(root)
    with inventory() as data:
        existing = next((p for p in data['projects'] if Path(p['path']).resolve() == root), None)
        if existing:
            return {'project': existing, 'created': False}
        label = re.sub(r'[\x00-\x1f\x7f]', ' ', config['name']).strip()[:80] or 'Android project'
        row = dict(id=uuid.uuid4().hex, name=label, path=str(root), task=config['task'], apk='', package=config['package'],
            auto=['task', 'package'], javaHome='', sdkHome='')
        data['projects'].append(row)
        return {'project': row, 'created': True}


def project_outputs(project):
    """Find APKs on demand, without traversing dependency and build caches."""
    try:
        root = Path(project['path']).resolve(strict=True)
        candidates = []
        if project.get('apk'):
            candidates.append(root / project['apk'])
        else:
            visited = 0
            for folder, dirs, _files in os.walk(root, followlinks=False):
                visited += 1
                if visited > 1000:
                    break
                if 'build' in dirs:
                    candidates.extend((Path(folder) / 'build/outputs/apk').glob('**/*.apk'))
                dirs[:] = [d for d in dirs if d not in ('build', 'node_modules', 'vendor') and not d.startswith('.')]
        outputs = []
        for path in candidates:
            resolved = path.resolve()
            if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.suffix.lower() != '.apk':
                continue
            stat = resolved.stat()
            outputs.append(dict(path=str(path.relative_to(root)), name=path.name, size=stat.st_size, modified=stat.st_mtime))
        return sorted(outputs, key=lambda row: row['modified'], reverse=True)[:30]
    except OSError:
        return []


def library():
    with inventory() as saved:
        projects, apks = saved['projects'], saved['apks']
    return {'projects': [{**p, 'outputs': project_outputs(p)} for p in projects], 'apks': apks}


def save_project(values):
    root = project_root(values['path'])
    import project_config
    values = {**values, **{key: values.get(key, '').strip() for key in ('task', 'package', 'javaHome', 'sdkHome')}}
    config = project_config.inspect(root, values)
    task = values['task'] or config['task']
    if not re.fullmatch(r':?[A-Za-z0-9_][A-Za-z0-9_:\-]{0,180}', task):
        raise ValueError('Enter one Gradle task, such as assembleDebug or :app:assembleDebug.')
    package = values['package'] or config['package']
    if package and not re.fullmatch(r'[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+', package, flags=re.ASCII):
        raise ValueError('Enter an Android application ID, such as com.example.app.')
    apk = values.get('apk', '').strip()
    if apk and (Path(apk).is_absolute() or '..' in Path(apk).parts or not apk.endswith('.apk')):
        raise ValueError('APK output must be a relative .apk path inside the project, or blank for discovery.')
    row = dict(id=values.get('id') or uuid.uuid4().hex, name=name(values.get('name') or config['name']), path=str(root), task=task, apk=apk, package=package,
        auto=[key for key in ('task', 'package') if not values[key]], javaHome=values['javaHome'], sdkHome=values['sdkHome'])
    with inventory() as data:
        if values.get('id'):
            item(data, 'projects', values['id'])
        data['projects'] = [p for p in data['projects'] if p['id'] != row['id']] + [row]
    return row


def save_apk(filename, project=None):
    source = Path(filename).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != '.apk':
        raise ValueError('Choose an APK file.')
    identifier = uuid.uuid4().hex
    target = home() / 'apks' / identifier / source.name
    target.parent.mkdir(parents=True, mode=0o700)
    try:
        shutil.copyfile(source, target)
        os.chmod(target, 0o600)
        digest = hashlib.sha256()
        with target.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        row = dict(id=identifier, name=source.name, path=str(target), source=str(source), project=project,
                   size=target.stat().st_size, savedAt=time.time(), sha256=digest.hexdigest())
        with inventory() as data:
            data['apks'].append(row)
        return row
    except BaseException:
        shutil.rmtree(target.parent)
        raise


def forget(kind, identifier):
    if kind not in ('projects', 'apks', 'device'):
        raise ValueError('Unsupported library item.')
    with inventory() as data:
        if kind == 'device':
            data['names'].pop(identifier, None)
        else:
            row = item(data, kind, identifier)
            if kind == 'apks':
                target = Path(row['path']).resolve()
                if not target.is_relative_to(home() / 'apks'):
                    raise ValueError('Saved APK is outside this workspace.')
                target.unlink(missing_ok=True)
            data[kind].remove(row)
    return {'ok': True}


def reservation(serial, enabled, token=None, reclaim=False):
    with inventory() as data:
        saved = data['reservations'].get(serial)
        token = saved['token'] if saved else token
        created = False
        if enabled and not token:
            record = coord.claim(serial, 'human:desktop:reserved', str(home()), 3600, 'Locked in Android Agent Lab', reclaim=reclaim)
            token, created = record['token'], True
        try:
            record = coord.reserve(serial, token, enabled)
        except BaseException:
            if created:
                coord.change_claim(serial, token, 'release')
            raise
        if enabled:
            data['reservations'][serial] = {'token': record['token']}
        else:
            data['reservations'].pop(serial, None)
        return record


def reservation_token(serial):
    with inventory() as data:
        saved = data['reservations'].get(serial)
        if not saved:
            return None
        record = coord.read_record(coord.record_path(serial))
        coord.check_owner(record, saved['token'])
        return saved['token']
