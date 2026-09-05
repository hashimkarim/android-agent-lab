#!/usr/bin/env python3
"""Small launcher for upstream Docker-Android and the shared ADB coordinator."""
import argparse
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import string
import subprocess
import sys
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills/adb-coordination/scripts"))
import adb_coord as coord


def config(root=ROOT):
    values = {"WEB_PORT": "8765", "ADB_PORT": "15555"}
    path = root / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                key, separator, value = line.partition("=")
                if not separator:
                    raise ValueError(f"Invalid .env line: {line!r}")
                values[key.strip()] = value.strip().strip("\"'")
    for key in ("WEB_PORT", "ADB_PORT", "VNC_PASSWORD"):
        if key in os.environ:
            values[key] = os.environ[key]
    for key in ("WEB_PORT", "ADB_PORT"):
        if not values[key].isdigit() or not 1024 <= int(values[key]) <= 65535:
            raise ValueError(f"{key} must be a port from 1024 to 65535")
    if values["WEB_PORT"] == values["ADB_PORT"]:
        raise ValueError("WEB_PORT and ADB_PORT must differ")
    for key in ("WEB_PORT", "ADB_PORT"):
        if values[key] != str(int(values[key])):
            raise ValueError(f"{key} must not contain leading zeros")
    password = values.get("VNC_PASSWORD", "")
    if password and (not password.isascii() or not password.isalnum() or len(password) > 8):
        raise ValueError("VNC_PASSWORD must contain 1–8 ASCII letters or digits")
    return values


def initialize(root=ROOT):
    path = root / ".env"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as out:
        password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        out.write(f"VNC_PASSWORD={password}\nWEB_PORT=8765\nADB_PORT=15555\n")
    return True


def compose(*args, capture=False, timeout=120):
    return subprocess.run(["docker", "compose", "--project-directory", str(ROOT), *args],
                          cwd=ROOT, capture_output=capture, text=True, timeout=timeout, check=False)


def device_serial(settings):
    return f"127.0.0.1:{settings['ADB_PORT']}"


def preview_url(settings, password=False):
    query = {"autoconnect": "true", "resize": "scale"}
    if password:
        query["password"] = settings.get("VNC_PASSWORD", "")
    return f"http://127.0.0.1:{settings['WEB_PORT']}/vnc.html?{urlencode(query)}"


def require_no_other_owner(record, token=None):
    if record and record["expires_at"] > time.time():
        if not token or not secrets.compare_digest(record["token"], token):
            raise coord.CoordinationError(f"Device is claimed by {record['owner']}; release it or supply its token before changing the container.")


def connect(serial, timeout=15):
    result = subprocess.run([coord.adb_binary(), "-L", coord.server_id(), "connect", serial],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode or not any(t in result.stdout.lower() for t in ["connected to", "already connected"]):
        raise coord.CoordinationError(result.stderr.strip() or result.stdout.strip() or "ADB connection failed")
    return result.stdout.strip()


def wait_ready(serial, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            connect(serial, timeout=max(.1, min(15, deadline - time.monotonic())))
            result = subprocess.run([coord.adb_binary(), "-L", coord.server_id(), "-s", serial,
                                     "shell", "getprop", "sys.boot_completed"],
                                    capture_output=True, timeout=max(.1, min(10, deadline - time.monotonic())))
            if result.returncode == 0 and result.stdout.strip() == b"1":
                return
        except (coord.CoordinationError, subprocess.TimeoutExpired):
            pass
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    raise coord.CoordinationError(f"Android did not finish booting within {timeout}s. Inspect: docker compose exec -T emulator tail -80 /home/androidusr/logs/device.stdout.log")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("status")
    sub.add_parser("connect")
    url = sub.add_parser("url")
    url.add_argument("--with-password", action="store_true", help="Include the local VNC password; do not share the resulting URL publicly")
    for name in ["up", "wait"]:
        p = sub.add_parser(name)
        p.add_argument("--timeout", type=int, default=300)
    down = sub.add_parser("down")
    down.add_argument("--token", default=os.environ.get("ADB_COORD_TOKEN"))
    p = sub.add_parser("claim")
    p.add_argument("--owner", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--ttl", type=float, default=1800)
    p.add_argument("--reclaim-expired", action="store_true")
    for name in ["renew", "release", "handoff", "adb", "screenshot"]:
        p = sub.add_parser(name)
        p.add_argument("--token", default=os.environ.get("ADB_COORD_TOKEN"))
        if name == "handoff":
            p.add_argument("--owner", required=True)
            p.add_argument("--note", default="")
        if name == "adb":
            p.add_argument("--timeout", type=float, default=120)
            p.add_argument("args", nargs=argparse.REMAINDER)
        if name == "screenshot":
            p.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        settings = config()
        serial = device_serial(settings)
        if args.action == "init":
            result = {"created": initialize(), "env_file": str(ROOT / ".env")}
        elif args.action == "doctor":
            checks = {"linux_x86_64": platform.system() == "Linux" and platform.machine() == "x86_64",
                      "kvm": os.access("/dev/kvm", os.R_OK | os.W_OK), "docker": bool(shutil.which("docker")),
                      "adb": False}
            try:
                checks["adb"] = bool(coord.adb_binary())
            except coord.CoordinationError:
                pass
            if checks["docker"]:
                checks["docker_daemon"] = subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
                checks["compose"] = compose("version", capture=True).returncode == 0
            print(json.dumps(checks, indent=2))
            return 0 if all(checks.values()) else 1
        elif args.action in {"up", "wait"}:
            if not 1 <= args.timeout <= 1800:
                raise ValueError("timeout must be 1–1800 seconds")
            if args.action == "up":
                initialize()
                settings = config()
                with coord.locked(serial) as path:
                    require_no_other_owner(coord.read_record(path))
                    if compose("up", "-d", "--build", timeout=900).returncode:
                        return 1
                print("Container started. Waiting for Android to finish booting…", flush=True)
            wait_ready(serial, args.timeout)
            result = {"ready": True, "serial": serial, "preview": preview_url(settings)}
        elif args.action == "down":
            with coord.locked(serial) as path:
                record = coord.read_record(path)
                require_no_other_owner(record, args.token)
                if compose("down").returncode:
                    return 1
                if record:
                    path.unlink()
            result = {"stopped": True, "android_data_preserved": True}
        elif args.action == "status":
            current = coord.read_record(coord.record_path(serial))
            runtime = compose("ps", "--format", "json", capture=True)
            if runtime.returncode:
                raise coord.CoordinationError(runtime.stderr.strip())
            result = {"serial": serial, "claim": coord.public_record(current) if current else None,
                      "containers": [json.loads(line) for line in runtime.stdout.splitlines() if line.strip()]}
        elif args.action == "url":
            print(preview_url(settings, args.with_password))
            return 0
        elif args.action == "connect":
            result = {"connection": connect(serial), "serial": serial}
        elif args.action == "claim":
            result = coord.claim(serial, args.owner, str(ROOT), args.ttl, args.note, args.reclaim_expired)
        elif args.action in {"renew", "release", "handoff"}:
            result = coord.change_claim(serial, args.token, args.action, getattr(args, "owner", None), getattr(args, "note", None))
        elif args.action == "adb":
            command = args.args[1:] if args.args[:1] == ["--"] else args.args
            return coord.run_adb(serial, args.token, command, args.timeout).returncode
        else:
            png = coord.screenshot(serial, args.token, renew=True)
            with open(args.out, "xb") as out:
                out.write(png)
            result = {"screenshot": str(Path(args.out).resolve())}
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, coord.CoordinationError, subprocess.TimeoutExpired) as exc:
        print(f"android-agent-lab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
