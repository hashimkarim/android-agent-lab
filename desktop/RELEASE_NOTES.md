Launch Android Agent Lab as a Linux desktop app, with the same interactive scrcpy
screen available in your browser preview and to coordinated agents.

- AppImage, DEB, RPM, Arch `.pkg.tar.zst`, and portable tar archives for x86_64 and ARM64.
- Device discovery, Android 16 Docker launcher, shared browser URLs, and agent instructions.
- Named agent cursors in both desktop and browser views.
- Bundled Chromium, Node, viewer, scrcpy server, and portable coordination skill.

Python 3.10+ and ADB are required for device sessions. Docker and KVM are needed
only for the included x86_64 emulator. ARM64 supports physical devices and remote
ADB. Packages target modern glibc Linux; updates are manual.

See [installation and usage](https://github.com/Hashim-K/android-agent-lab/blob/main/docs/desktop.md).
For a user-local AppImage menu launcher, download `install_appimage.py` and run
`python3 install_appimage.py ./Android-Agent-Lab-0.1.0-x86_64.AppImage`.
Verify downloads with `sha256sum -c SHA256SUMS --ignore-missing`.
