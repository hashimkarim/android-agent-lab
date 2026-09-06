#!/usr/bin/env python3
"""Stage only redistributable runtime files; no claims, credentials, or device data."""
import shutil
import subprocess
from pathlib import Path
import urllib.request

import video

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / '.desktop-build/runtime'


def main():
    video.setup()
    if TARGET.exists():
        shutil.rmtree(TARGET)
    for directory in ('scripts', 'viewer/public', 'vendor'):
        (TARGET / directory).mkdir(parents=True, exist_ok=True)
    for name in ('lab.py', 'video.py', 'desktop_rpc.py', 'control_broker.py', 'device_tools.py', 'workspace.py', 'desktop_jobs.py', 'project_config.py'):
        shutil.copy2(ROOT / 'scripts' / name, TARGET / 'scripts' / name)
    shutil.copytree(ROOT / 'skills', TARGET / 'skills', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('compose.yaml', 'Dockerfile', '.dockerignore', 'LICENSE'):
        shutil.copy2(ROOT / name, TARGET / name)
    for name in ('server.mjs', 'control.mjs', 'broker.mjs', 'options.mjs', 'library.mjs', 'package.json', 'package-lock.json'):
        shutil.copy2(ROOT / 'viewer' / name, TARGET / 'viewer' / name)
    shutil.copytree(ROOT / 'viewer/public', TARGET / 'viewer/public', dirs_exist_ok=True)
    shutil.copy2(video.SERVER, TARGET / 'vendor' / video.SERVER.name)
    url = f'https://raw.githubusercontent.com/Genymobile/scrcpy/v{video.SERVER_VERSION}/LICENSE'
    with urllib.request.urlopen(url, timeout=30) as response:
        (TARGET / 'vendor/scrcpy-LICENSE').write_bytes(response.read(100_000))
    subprocess.run(['npm', 'ci', '--omit=dev', '--ignore-scripts', '--prefix', str(TARGET / 'viewer')], check=True)
    print(f'Desktop runtime staged in {TARGET}')


if __name__ == '__main__':
    main()
