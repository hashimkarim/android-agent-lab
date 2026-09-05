#!/usr/bin/env python3
"""Install an Android Agent Lab AppImage and application-menu entry for this user."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('appimage', type=Path)
    parser.add_argument('--extract-and-run', action='store_true', help='Use the AppImage fallback for systems without FUSE')
    args = parser.parse_args()
    source = args.appimage.resolve(strict=True)
    home = Path.home()
    destination = home / '.local/opt/android-agent-lab/Android-Agent-Lab.AppImage'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix('.new')
    shutil.copyfile(source, temp)
    temp.chmod(0o755)
    data = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share')))
    icon = data / 'icons/hicolor/256x256/apps/android-agent-lab.png'
    # The root icon is a symlink. Extract its actual file without the whole app.
    icon_path = 'usr/share/icons/hicolor/256x256/apps/android-agent-lab.png'
    try:
        with tempfile.TemporaryDirectory(prefix='android-agent-lab-icon-') as directory:
            subprocess.run([str(temp), '--appimage-extract', icon_path], cwd=directory, check=True, stdout=subprocess.DEVNULL)
            icon.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(directory) / 'squashfs-root' / icon_path, icon)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    launcher = home / '.local/bin/android-agent-lab'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    extra = ' --appimage-extract-and-run' if args.extract_and_run else ''
    launcher.write_text('#!/bin/sh\nunset ELECTRON_RUN_AS_NODE\nexec ' + shlex.quote(str(destination)) + extra + ' "$@"\n')
    launcher.chmod(0o755)
    entry = data / 'applications/android-agent-lab.desktop'
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text('[Desktop Entry]\nType=Application\nName=Android Agent Lab\n'
                     'Comment=Shared Android devices and agent cursors\n'
                     f'Exec={desktop_quote(launcher)}\nIcon=android-agent-lab\n'
                     'Terminal=false\nCategories=Development;\nStartupWMClass=android-agent-lab\n')
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(entry.parent)], check=False)
    print(f'Installed: {destination}\nLaunch Android Agent Lab from your application menu or {launcher}')


if __name__ == '__main__':
    main()
