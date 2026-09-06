#!/usr/bin/env bash
set -euo pipefail
trap 'chown -R "$PUBLISH_UID:$PUBLISH_GID" /results' EXIT
dnf install -y rpm-build coreutils tar gzip python3 android-tools avahi-tools gtk3 nss libXScrnSaver libXtst xdg-utils at-spi2-core libuuid libsecret mesa-libgbm alsa-lib xorg-x11-server-Xvfb xorg-x11-xauth
cp -a /prepared/rpm /tmp/rpm
rpmbuild -ba --define '_topdir /tmp/rpm' --define '_smp_build_ncpus 2' /tmp/rpm/SPECS/android-agent-lab.spec
cp /tmp/rpm/SRPMS/*.src.rpm /results/
dnf install -y /tmp/rpm/RPMS/x86_64/*.rpm
useradd -m tester
runuser -u tester -- env ADB_LAB_USER_DATA=/tmp/aal-smoke xvfb-run -a android-agent-lab --smoke-test
