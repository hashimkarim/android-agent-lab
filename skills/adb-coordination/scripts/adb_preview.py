#!/usr/bin/env python3
"""Loopback Android screenshot preview, with optional claim-checked input."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import urlsplit

from adb_coord import CoordinationError, check_owner, locked, read_record, run_adb, screenshot


def input_command(data):
    if not isinstance(data, dict):
        raise ValueError("Expected an input object.")
    kind = data.get("kind")
    if not isinstance(kind, str):
        raise ValueError("Expected an input kind string.")
    if kind == "key" and isinstance(data.get("key"), str) and data["key"] in {"BACK", "HOME", "APP_SWITCH", "ENTER"}:
        return ["shell", "input", "keyevent", "KEYCODE_" + data["key"]]
    keys = {"tap": ("x", "y"), "swipe": ("x", "y", "x2", "y2")}.get(kind)
    if keys and all(type(data.get(k)) is int and 0 <= data[k] <= 16384 for k in keys):
        return ["shell", "input", kind, *[str(data[k]) for k in keys], *(["300"] if kind == "swipe" else [])]
    raise ValueError("Expected bounded tap/swipe coordinates or a supported navigation key.")


def make_handler(serial, token, key, control):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, data, content_type="application/json"):
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self, authenticate=True):
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in hosts or (origin and origin not in {"http://" + h for h in hosts}):
                self.reply(403, {"error": "Loopback origin required."})
                return False
            if authenticate and not secrets.compare_digest(self.headers.get("X-ADB-Preview-Key", ""), key):
                self.reply(403, {"error": "Open the complete preview URL printed by the server."})
                return False
            return True

        def do_GET(self):
            route = urlsplit(self.path).path
            if not self.allowed(authenticate=route != "/"):
                return
            try:
                if route == "/":
                    self.reply(200, (Path(__file__).resolve().parent.parent / "assets/preview.html").read_bytes(), "text/html; charset=utf-8")
                elif route == "/status":
                    with locked(serial) as path:
                        record = read_record(path)
                        check_owner(record, token)
                    self.reply(200, {"serial": serial, "owner": record["owner"], "control": control,
                                     "expires_at": record["expires_at"]})
                elif route == "/frame":
                    self.reply(200, screenshot(serial, token), "image/png")
                else:
                    self.reply(404, {"error": "Unknown route."})
            except (CoordinationError, OSError, subprocess.TimeoutExpired) as exc:
                self.reply(409, {"error": str(exc)})

        def do_POST(self):
            if not self.allowed():
                return
            if urlsplit(self.path).path != "/input" or not control:
                self.reply(403, {"error": "Input is disabled for this preview."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Expected a small JSON input request.")
                command = input_command(json.loads(self.rfile.read(length)))
                result = run_adb(serial, token, command, timeout=15, capture=True)
                if result.returncode:
                    raise CoordinationError(result.stderr.decode(errors="replace") or "Input failed.")
                self.reply(200, {"ok": True})
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {"error": str(exc)})
            except (CoordinationError, OSError, subprocess.TimeoutExpired) as exc:
                self.reply(409, {"error": str(exc)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--token", default=os.environ.get("ADB_COORD_TOKEN"))
    parser.add_argument("--port", type=int, default=0, help="0 chooses a free port")
    parser.add_argument("--control", action="store_true", help="Enable tap, swipe, Back, Home, and Recents")
    parser.add_argument("--duration", type=int, default=1800, help="Maximum server lifetime in seconds")
    args = parser.parse_args()
    if not 1 <= args.duration <= 86400:
        parser.error("duration must be between 1 and 86400 seconds")
    try:
        with locked(args.serial) as path:
            check_owner(read_record(path), args.token)
        key = secrets.token_urlsafe(32)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.serial, args.token, key, args.control))
        server.daemon_threads = True
        server.timeout = 1
        print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/#key={key}",
                          "pid": os.getpid(), "serial": args.serial, "control": args.control,
                          "duration": args.duration}), flush=True)
        deadline = time.monotonic() + args.duration
        with server:
            while time.monotonic() < deadline:
                server.handle_request()
        return 0
    except KeyboardInterrupt:
        return 0
    except (CoordinationError, OSError) as exc:
        print(f"adb-preview: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
