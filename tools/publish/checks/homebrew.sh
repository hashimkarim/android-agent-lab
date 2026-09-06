#!/usr/bin/env bash
set -euo pipefail
# The official image includes an unrelated GitHub CLI APT repository with an
# expired key. This test only needs Ubuntu's desktop libraries; leave signature
# verification enabled and remove that extra source inside this container.
sudo rm -f /etc/apt/sources.list.d/github-cli.list
sudo apt-get update
alsa=libasound2
if apt-cache show libasound2t64 > /dev/null 2>&1; then alsa=libasound2t64; fi
sudo apt-get install -y xvfb xauth libgtk-3-0 libnss3 libgbm1 "$alsa" libsecret-1-0 libxss1 libxtst6 libatspi2.0-0
brew tap-new --no-git aal-ci/packages
cp /prepared/homebrew/Formula/android-agent-lab.rb "$(brew --repository aal-ci/packages)/Formula/"
brew install --formula aal-ci/packages/android-agent-lab
brew test aal-ci/packages/android-agent-lab
ADB_LAB_USER_DATA=/tmp/aal-smoke xvfb-run -a android-agent-lab --smoke-test
