# syntax=docker/dockerfile:1
# Reuse upstream's emulator, noVNC, desktop controls, and process management.
FROM budtmo/docker-android:emulator_14.0@sha256:5313cd59712871c9462b04a5dbabd40e13eaa9d66706c53bb90b1d7939a48bae

USER 0

# Install the stable Android 16 / API 36.1 update from SDK channel 0.
# The upstream image already contains Android SDK license acceptance files.
RUN sdkmanager --channel=0 'system-images;android-36.1;google_apis;x86_64'

# The public upstream launcher has a fixed version-to-API table ending at 14.
# Add the version mapping and recognize the SDK's normalized Pixel profile name.
RUN python3 - <<'PY'
from pathlib import Path
path = Path('/home/androidusr/docker-android/cli/src/device/emulator.py')
source = path.read_text()
anchor = '    API_LEVEL = {\n'
assert source.count(anchor) == 1, 'Upstream API table changed; review this adapter'
source = source.replace(anchor, anchor + '        # Android Agent Lab modification: Android 16 / API 36.1.\n        "16.0": "36.1",\n')
# The SDK writes pixel_9, while upstream checks Pixel 9 and recreates the AVD.
anchor = "re.match(r'hw\\.device\\.name ?= ?{}'.format(self.device), line)"
assert source.count(anchor) == 1, 'Upstream device check changed; review this adapter'
source = source.replace(anchor, "re.fullmatch(r'hw\\.device\\.name\\s*=\\s*' + re.escape(self.file_name if 'pixel' in self.device.lower() else self.device), line.strip())")
path.write_text(source)
for directory in ('emulator', '.android'):
    target = Path('/home/androidusr') / directory
    target.mkdir(exist_ok=True)
    import os
    os.chown(target, 1300, 1301)
PY

ENV EMULATOR_ANDROID_VERSION=16.0 \
    EMULATOR_API_LEVEL=36.1

USER 1300:1301
