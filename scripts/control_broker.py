#!/usr/bin/env python3
"""Keep the shared POSIX operation lock for one live scrcpy gesture.

Only claim acquisition/release cross this pipe. Motion packets go straight from
the viewer to scrcpy, without Python, ADB shell, or disk writes per movement.
"""
import json
import os
from pathlib import Path
import selectors
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/adb-coordination/scripts'))
import adb_coord as coord


def feedback(data):
    event = {'id': str(data['id'])[:80], 'actor': coord.activity_actor(data['actor']),
             'kind': data.get('kind', 'key')}
    if event['kind'] not in {'pointer', 'typing', 'key', 'scroll'}:
        raise ValueError('Invalid feedback kind')
    if 'points' in data:
        points = data['points']
        if not isinstance(points, list) or len(points) != 2 or not all(isinstance(p, (int, float)) and 0 <= p <= 16384 for p in points):
            raise ValueError('Invalid pointer feedback')
        event['points'] = points
    # Never copy text/clipboard contents or arbitrary user fields into activity.
    return event


class Broker:
    def __init__(self, config):
        self.config = config
        self.lock = self.path = self.record = self.event = None
        self.started = 0

    def acquire(self, event):
        if self.lock:
            raise coord.CoordinationError('A gesture already holds the device')
        event = feedback(event)
        lock = coord.locked(self.config['serial'])
        path = lock.__enter__()
        try:
            record = coord.read_record(path)
            coord.check_owner(record, self.config['token'])
            record['expires_at'] = 2**40 if record.get('reserved') else time.time() + record['ttl']
            coord.save_record(path, record, durable=False)
            coord.publish_activity(path, record, {**event, 'phase':'start'})
        except BaseException:
            lock.__exit__(*sys.exc_info())
            raise
        self.lock, self.path, self.record, self.event = lock, path, record, event
        self.started = time.monotonic()

    def release(self, event=None, ok=True):
        if not self.lock:
            return
        try:
            record = coord.read_record(self.path)
            coord.check_owner(record, self.config['token'], allow_expired=True)
            final = feedback(event) if event else self.event
            # Preserve the original attribution, including when the client disconnects.
            final.update(id=self.event['id'], actor=self.event['actor'])
            coord.publish_activity(self.path, record, {**final, 'phase':'complete', 'ok':bool(ok)})
            record['expires_at'] = 2**40 if record.get('reserved') else time.time() + record['ttl']
            coord.save_record(self.path, record, durable=False)
        finally:
            self.lock.__exit__(None, None, None)
            self.lock = None


def main():
    config = json.loads(os.environ['ADB_VIDEO_CONFIG'])
    if not config['control']:
        raise SystemExit('Read-only session')
    broker = Broker(config)
    buffer = b''
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(sys.stdin, selectors.EVENT_READ)
            while True:
                if broker.lock and time.monotonic() - broker.started > 60:
                    raise RuntimeError('Control watchdog expired')
                if not selector.select(1):
                    continue
                chunk = os.read(sys.stdin.fileno(), 65536)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > 65536:
                    raise ValueError('Control request too large')
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    request = json.loads(line)
                    result = {'id':request['id']}
                    try:
                        if request['action'] == 'acquire':
                            broker.acquire(request['event'])
                        elif request['action'] == 'release':
                            broker.release(request.get('event'), request.get('ok', True))
                        else:
                            raise ValueError('Unknown control operation')
                        result['ok'] = True
                    except (ValueError, OSError, coord.CoordinationError) as exc:
                        result.update(ok=False, error=str(exc))
                    print(json.dumps(result), flush=True)
    finally:
        broker.release(ok=False)


if __name__ == '__main__':
    main()
