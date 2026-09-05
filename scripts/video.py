#!/usr/bin/env python3
"""Claim-aware browser video using the upstream scrcpy server and Tango client."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shlex
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'skills/adb-coordination/scripts'))
import adb_coord as coord
from adb_preview import input_command

SERVER_VERSION = '3.3.3'
SERVER_SHA256 = '7e70323ba7f259649dd4acce97ac4fefbae8102b2c6d91e2e7be613fd5354be0'
SERVER = Path(os.environ.get('ADB_VIDEO_SERVER', str(ROOT / '.lab' / f'scrcpy-server-v{SERVER_VERSION}')))


def verify_server(path=SERVER):
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != SERVER_SHA256:
        raise coord.CoordinationError('Missing or invalid scrcpy server; run python3 scripts/video.py setup')


def setup():
    subprocess.run(['npm', 'ci', '--prefix', str(ROOT / 'viewer')], check=True, timeout=300)
    subprocess.run(['npm', 'run', 'build', '--prefix', str(ROOT / 'viewer')], check=True, timeout=120)
    SERVER.parent.mkdir(mode=0o700, exist_ok=True)
    if not SERVER.exists():
        url = f'https://github.com/Genymobile/scrcpy/releases/download/v{SERVER_VERSION}/scrcpy-server-v{SERVER_VERSION}'
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(10_000_000)
        if hashlib.sha256(data).hexdigest() != SERVER_SHA256:
            raise coord.CoordinationError('Downloaded scrcpy server checksum does not match')
        with SERVER.open('xb') as out:
            out.write(data)
    verify_server()
    print('Browser video dependencies are ready.')


def video_input(data):
    if isinstance(data, dict) and data.get('kind') == 'text':
        value = data.get('text')
        if not isinstance(value, str) or not 1 <= len(value) <= 500 or any(not 32 <= ord(c) <= 126 for c in value) or '%s' in value:
            raise ValueError('Use 1–500 printable ASCII characters; literal %s is unsupported by ADB text input.')
        # ADB shell joins arguments into shell text. Quote user text explicitly.
        return ['shell', 'input', 'text', shlex.quote(value.replace(' ', '%s'))]
    if isinstance(data, dict) and data.get('kind') == 'key' and isinstance(data.get('key'), str) and data['key'] in {'DEL', 'TAB', 'DPAD_LEFT', 'DPAD_RIGHT', 'DPAD_UP', 'DPAD_DOWN'}:
        return ['shell', 'input', 'keyevent', 'KEYCODE_' + data['key']]
    return input_command(data)


def rpc():
    config = json.loads(os.environ['ADB_VIDEO_CONFIG'])
    data = json.loads(sys.stdin.buffer.read(4097))
    if not config['control']:
        raise coord.CoordinationError('This viewer is read-only')
    actor = coord.activity_actor(data.get('actor', 'human:browser')) if isinstance(data, dict) else None
    result = coord.run_adb(config['serial'], config['token'], video_input(data), timeout=15, capture=True, actor=actor)
    if result.returncode:
        raise coord.CoordinationError(result.stderr.decode(errors='replace') or 'Device input failed')
    print(json.dumps({'ok': True}))


def endpoint(value):
    match = re.fullmatch(r'tcp:(\[[^\]]+\]|[^:]+):(\d+)', value)
    if not match or not 1 <= int(match[2]) <= 65535:
        raise ValueError('Video currently requires a tcp:HOST:PORT ADB_SERVER_SOCKET')
    return {'host': match[1].strip('[]'), 'port': int(match[2])}


def node_launch(config):
    """Packaged desktop apps reuse their bundled Node; source installs use PATH."""
    env = {**os.environ, 'ADB_VIDEO_CONFIG': json.dumps(config)}
    if os.environ.get('ADB_VIDEO_ELECTRON_NODE') == '1':
        env['ELECTRON_RUN_AS_NODE'] = '1'
    return [os.environ.get('ADB_VIDEO_NODE', 'node'), str(ROOT / 'viewer/server.mjs')], env


def release_owned(serial, token):
    # A finishing input may still hold the lock. Never release a replacement owner.
    for _ in range(20):
        try:
            coord.change_claim(serial, token, 'release')
            return
        except coord.CoordinationError:
            record = coord.read_record(coord.record_path(serial))
            if not record or not secrets.compare_digest(record['token'], token):
                return
            time.sleep(.25)


def start(args):
    verify_server()
    if not (ROOT / 'viewer/public/client.js').is_file():
        raise coord.CoordinationError('Run python3 scripts/video.py setup first')
    if not 1 <= args.duration <= 86400 or not 320 <= args.max_size <= 4096 or not 1 <= args.max_fps <= 120 or not 0 <= args.port <= 65535:
        raise ValueError('Invalid duration, size, FPS, or port')
    child = None
    try:
        with coord.locked(args.serial) as path:
            record = coord.read_record(path)
            coord.check_owner(record, args.token)
            size = subprocess.run([coord.adb_binary(), '-L', coord.server_id(), '-s', args.serial, 'shell', 'wm', 'size'], capture_output=True, text=True, timeout=10, check=True)
            dimensions = re.findall(r'(?:Physical|Override) size:\s*(\d+)x(\d+)', size.stdout)
            if not dimensions:
                raise coord.CoordinationError('Cannot determine device display size')
            width, height = map(int, dimensions[-1])
            config = dict(serial=args.serial, token=args.token, record=str(path), activity=str(path.with_suffix('.activity')), server=coord.server_id(),
                          endpoint=endpoint(coord.server_id()), key=secrets.token_urlsafe(32), port=args.port,
                          control=args.control, maxSize=args.max_size, maxFps=args.max_fps,
                          width=width, height=height, serverFile=str(SERVER), python=sys.executable, supervisor=os.getpid())
            command, env = node_launch(config)
            child = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, text=True)
            # Hold the operation lock through server upload/start, then let ADB commands run.
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                if not selector.select(45):
                    raise coord.CoordinationError('Scrcpy startup timed out')
                line = child.stdout.readline()
            if not line:
                raise coord.CoordinationError('Scrcpy startup failed; inspect the error above')
            info = json.loads(line)
            info.update(pid=os.getpid(), duration=args.duration)
            print(json.dumps(info), flush=True)
        deadline = time.monotonic() + args.duration
        while child.poll() is None and time.monotonic() < deadline:
            time.sleep(.25)
            if getattr(args, 'parent_pid', None) and os.getppid() != args.parent_pid:
                break
            # Atomic record replacement makes this passive read safe. It must not renew.
            coord.check_owner(coord.read_record(coord.record_path(args.serial)), args.token)
        if child.poll() not in (None, 0):
            raise coord.CoordinationError('Video process stopped unexpectedly')
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if getattr(args, 'release_on_exit', False):
            release_owned(args.serial, args.token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('setup')
    sub.add_parser('rpc', help=argparse.SUPPRESS)
    p = sub.add_parser('start')
    p.add_argument('--serial', required=True)
    p.add_argument('--token', default=os.environ.get('ADB_COORD_TOKEN'))
    p.add_argument('--control', action='store_true')
    p.add_argument('--port', type=int, default=0)
    p.add_argument('--duration', type=int, default=1800)
    p.add_argument('--max-size', type=int, default=1280)
    p.add_argument('--max-fps', type=int, default=30)
    p.add_argument('--parent-pid', type=int, help=argparse.SUPPRESS)
    p.add_argument('--release-on-exit', action='store_true', help='Release this token when the desktop-owned session stops')
    args = parser.parse_args()
    def interrupted(*_):
        raise KeyboardInterrupt
    if args.action == 'start':
        signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.action == 'setup':
            setup()
        elif args.action == 'rpc':
            rpc()
        else:
            start(args)
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, coord.CoordinationError, subprocess.SubprocessError) as exc:
        print(f'adb-video: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
