Dragging now controls Android continuously through scrcpy: touch-down and movement
reach the device before mouse release. The shared device lock covers the whole
gesture, including cancellation on disconnect.

- Two cursor modes: **Agents only** and **Agents and user**. Human pointers are
  small circles that follow hover continuously; agent pointers keep names and colors.
- Developer toolbars outside the phone screen: navigation, power, volume,
  rotation, notifications, screenshots, recording, APK installation, Logcat,
  UI hierarchy, Android settings, zoom, and fullscreen.
- Explicit Unicode clipboard paste, mouse-wheel scrolling, and a 60 FPS video cap.
- AppImage, DEB, RPM, Arch packages, and tar archives for x86_64 and ARM64.

Validated on the Android 16 / API 36.1 Docker emulator, including app updates
while the mouse remains held, shared gesture locking, hover across viewers,
cursor filtering, and the developer tools. Device rendering and encoding still
affect latency; there is no end-to-end latency guarantee.

Python 3.10+ and ADB are required. Docker/KVM are needed only for the included
x86_64 emulator. ARM64 supports physical devices and remote ADB. Packages target
modern glibc Linux; updates are manual.

See [installation and usage](https://github.com/Hashim-K/android-agent-lab/blob/main/docs/desktop.md).
For a user-local AppImage menu launcher, download `install_appimage.py` and run
`python3 install_appimage.py ./Android-Agent-Lab-0.2.0-x86_64.AppImage`.
Verify downloads with `sha256sum -c SHA256SUMS --ignore-missing`.
