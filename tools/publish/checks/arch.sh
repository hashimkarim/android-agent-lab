#!/usr/bin/env bash
set -euo pipefail
trap 'chown -R "$PUBLISH_UID:$PUBLISH_GID" /results' EXIT
pacman -Syu --noconfirm --needed git python android-tools avahi gtk3 nss libxss libxtst xdg-utils at-spi2-core util-linux-libs libsecret libglvnd mesa alsa-lib xorg-server-xvfb xorg-xauth
useradd -m builder
cp -a /prepared/aur /tmp/package
chown -R builder:builder /tmp/package
cd /tmp/package
runuser -u builder -- makepkg --verifysource --noconfirm
runuser -u builder -- makepkg --printsrcinfo > /results/.SRCINFO
runuser -u builder -- makepkg --nodeps --noconfirm
pacman -U --noconfirm ./*.pkg.tar.zst
test -f /usr/lib/android-agent-lab/resources/runtime/skills/adb-coordination/SKILL.md
runuser -u builder -- env ADB_LAB_USER_DATA=/tmp/aal-smoke xvfb-run -a android-agent-lab --smoke-test
