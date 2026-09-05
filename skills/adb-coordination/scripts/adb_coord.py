#!/usr/bin/env python3
"""Cooperative per-device ownership and serialized ADB execution (POSIX, stdlib)."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time


class CoordinationError(RuntimeError):
    pass


def state_dir():
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    path = Path(os.environ.get("ADB_COORD_STATE", str(base / "adb-coordination"))).expanduser()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def adb_binary():
    override = os.environ.get("ADB_COORD_ADB")
    if override:
        return override
    found = shutil.which("adb")
    if found:
        return found
    for root in [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                 str(Path.home() / "Android/Sdk"), str(Path.home() / "Library/Android/sdk")]:
        if root and (Path(root) / "platform-tools/adb").is_file():
            return str(Path(root) / "platform-tools/adb")
    raise CoordinationError("ADB unavailable; install Android SDK platform-tools or set ADB_COORD_ADB.")


def server_id():
    # Pin the actual endpoint into each claim; aliases are deliberately conservative.
    return os.environ.get("ADB_SERVER_SOCKET", "tcp:localhost:5037")


def record_path(serial):
    if not serial or serial.startswith("-"):
        raise CoordinationError("An explicit, non-option device serial is required.")
    return state_dir() / (hashlib.sha256(serial.encode()).hexdigest() + ".json")


@contextmanager
def locked(serial):
    path = record_path(serial)
    # Never unlink lock files: replacing one could let two processes lock different inodes.
    fd = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CoordinationError(f"Device {serial} has an operation in progress; retry after it finishes.")
        try:
            yield path
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read_record(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (ValueError, OSError) as exc:
        raise CoordinationError(f"Cannot read claim {path}: {exc}; do not bypass coordination.") from exc


def save_record(path, record):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".claim-")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(record, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def check_owner(record, token, *, allow_expired=False):
    if not record or not token or not secrets.compare_digest(record["token"], token):
        raise CoordinationError("Claim token does not own this device; inspect status or request a handoff.")
    if record["server"] != server_id():
        raise CoordinationError("ADB_SERVER_SOCKET differs from the claim's endpoint.")
    if not allow_expired and record["expires_at"] <= time.time():
        raise CoordinationError("Claim expired; inspect status and explicitly renew or reclaim it.")


def public_record(record):
    return {**{k: v for k, v in record.items() if k != "token"},
            "expired": record["expires_at"] <= time.time()}


def validate_ttl(ttl):
    if not math.isfinite(ttl) or not 1 <= ttl <= 86400:
        raise CoordinationError("TTL must be between 1 and 86400 seconds.")


def claim(serial, owner, project, ttl=1800, note="", reclaim=False):
    validate_ttl(ttl)
    with locked(serial) as path:
        old = read_record(path)
        if old and (old["expires_at"] > time.time() or not reclaim):
            raise CoordinationError("Device already claimed: " + json.dumps(public_record(old)))
        record = dict(serial=serial, owner=owner, project=str(Path(project).resolve()),
                      token=secrets.token_urlsafe(24), server=server_id(), ttl=ttl,
                      expires_at=time.time() + ttl, note=note)
        save_record(path, record)
        return record


def change_claim(serial, token, action, owner=None, note=None, ttl=None):
    with locked(serial) as path:
        record = read_record(path)
        check_owner(record, token, allow_expired=action in {"release", "renew"})
        if action == "release":
            path.unlink()
            return {"released": serial}
        if ttl is not None:
            validate_ttl(ttl)
            record["ttl"] = ttl
        if action == "handoff":
            if not owner:
                raise CoordinationError("Handoff requires the next thread's owner label.")
            record["previous_owner"] = record["owner"]
            record["owner"] = owner
            record["token"] = secrets.token_urlsafe(24)
        if note is not None:
            record["note"] = note
        record["expires_at"] = time.time() + record["ttl"]
        save_record(path, record)
        return record


DEVICE_COMMANDS = {"shell", "exec-out", "install", "install-multiple", "install-multi-package",
                   "uninstall", "push", "pull", "logcat", "forward", "reverse", "bugreport",
                   "get-state", "get-serialno", "get-devpath", "wait-for-device", "emu"}


def run_adb(serial, token, args, timeout=120, *, capture=False, renew=True):
    if not args or args[0] not in DEVICE_COMMANDS:
        raise CoordinationError("Use a device command after --; server-wide commands and target overrides are excluded.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise CoordinationError("Timeout must be finite and positive.")
    with locked(serial) as path:
        record = read_record(path)
        check_owner(record, token)
        if renew:
            record["expires_at"] = time.time() + record["ttl"]
            save_record(path, record)
        try:
            # The explicit socket prevents legacy host/port environment settings from retargeting ADB.
            return subprocess.run([adb_binary(), "-L", record["server"], "-s", serial, *args],
                                  timeout=timeout, capture_output=capture, check=False)
        finally:
            if renew:
                record["expires_at"] = time.time() + record["ttl"]
                save_record(path, record)


def screenshot(serial, token, *, renew=False):
    result = run_adb(serial, token, ["exec-out", "screencap", "-p"], timeout=20,
                     capture=True, renew=renew)
    if result.returncode:
        raise CoordinationError(result.stderr.decode(errors="replace").strip() or "Screenshot failed.")
    if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise CoordinationError("Device did not return a PNG screenshot.")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("devices")
    sub.add_parser("status")
    for action in ["claim", "renew", "release", "handoff", "run", "screenshot"]:
        cmd = sub.add_parser(action)
        cmd.add_argument("--serial", required=True)
        if action != "claim":
            cmd.add_argument("--token", default=os.environ.get("ADB_COORD_TOKEN"))
        if action in {"claim", "handoff"}:
            cmd.add_argument("--owner", required=True, help="client:thread-id or a unique task label")
        if action in {"claim", "renew", "handoff"}:
            cmd.add_argument("--note", default="" if action == "claim" else None)
            cmd.add_argument("--ttl", type=float, default=1800 if action == "claim" else None)
        if action == "claim":
            cmd.add_argument("--project", default=os.getcwd())
            cmd.add_argument("--reclaim-expired", action="store_true")
        if action == "run":
            cmd.add_argument("--timeout", type=float, default=120)
            cmd.add_argument("args", nargs=argparse.REMAINDER)
        if action == "screenshot":
            cmd.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.action == "devices":
            return subprocess.run([adb_binary(), "-L", server_id(), "devices", "-l"], timeout=15).returncode
        if args.action == "status":
            result = [public_record(r) for p in sorted(state_dir().glob("*.json")) if (r := read_record(p))]
        elif args.action == "claim":
            result = claim(args.serial, args.owner, args.project, args.ttl, args.note, args.reclaim_expired)
        elif args.action in {"release", "renew", "handoff"}:
            result = change_claim(args.serial, args.token, args.action, getattr(args, "owner", None),
                                  getattr(args, "note", None), getattr(args, "ttl", None))
        elif args.action == "run":
            command = args.args[1:] if args.args[:1] == ["--"] else args.args
            return run_adb(args.serial, args.token, command, args.timeout).returncode
        else:
            data = screenshot(args.serial, args.token, renew=True)
            with open(args.out, "xb") as out:
                out.write(data)
            result = {"screenshot": str(Path(args.out).resolve())}
        print(json.dumps(result, indent=2))
        return 0
    except (CoordinationError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"adb-coordination: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
