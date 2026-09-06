#!/usr/bin/env bash
set -euo pipefail
trap 'chown -R "$PUBLISH_UID:$PUBLISH_GID" /results' EXIT
export DEBIAN_FRONTEND=noninteractive
export DEB_BUILD_OPTIONS=parallel=2
apt-get update
apt-get install -y --no-install-recommends build-essential debhelper dh-apparmor devscripts dpkg-dev xvfb xauth python3 adb avahi-utils libgtk-3-0 libnss3 libxss1 libxtst6 xdg-utils libatspi2.0-0 libuuid1 libsecret-1-0 libgbm1 libasound2t64 ca-certificates
cp -a /prepared/ppa /tmp/ppa
cd /tmp/ppa/android-agent-lab-*
dpkg-buildpackage -S -sa -us -uc -d
cd /tmp/ppa
# Build from the submitted source, not just the working directory.
dpkg-source -x ./*.dsc extracted
cd extracted
dpkg-buildpackage -b -us -uc
apt-get install -y /tmp/ppa/*.deb
python3 - <<'PY'
from pathlib import Path
invalid = [str(p) for p in Path('/opt/android-agent-lab').rglob('*') if p.lstat().st_mtime < 946684800]
if invalid:
    raise SystemExit('Launchpad rejects old payload timestamps: ' + ', '.join(invalid[:5]))
PY
cp /tmp/ppa/*.{dsc,changes,buildinfo,orig.tar.gz,debian.tar.xz} /results/
useradd -m tester
runuser -u tester -- env ADB_LAB_USER_DATA=/tmp/aal-smoke xvfb-run -a android-agent-lab --smoke-test
