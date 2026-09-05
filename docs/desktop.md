# Linux desktop app

Download an installer from [Releases](https://github.com/Hashim-K/android-agent-lab/releases).
For package manager installation and updates, see the
[AUR, Homebrew, COPR, and Ubuntu PPA instructions](distribution.md).
The app includes Chromium, Node, the scrcpy server, the viewer, and the coordination
skill. It opens a normal desktop window and serves the **same Android screen** on
a private localhost browser port. Agent cursors appear in both views.

## Choose a package

| System | Package | Install |
| --- | --- | --- |
| Ubuntu, Debian, Mint, Pop!_OS | `.deb` | `sudo apt install ./Android-Agent-Lab-*.deb` |
| Fedora and compatible RPM distributions | `.rpm` | `sudo dnf install ./Android-Agent-Lab-*.rpm` |
| openSUSE | `.rpm` | `sudo zypper install ./Android-Agent-Lab-*.rpm` |
| Arch, EndeavourOS, Manjaro | `.pkg.tar.zst` | `sudo pacman -U ./Android-Agent-Lab-*.pkg.tar.zst` |
| Other mainstream Linux desktops | `.AppImage` | Make executable, then launch it |
| Manual installations | `.tar.gz` | Extract and run `android-agent-lab` inside the directory |

Download only the package for your architecture. `x64`, `amd64`, and `x86_64`
mean 64-bit Intel/AMD; `arm64` and `aarch64` mean 64-bit ARM. These builds target
modern **glibc Linux** with X11 or Wayland. Alpine/musl, 32-bit machines, and old
Linux releases are outside the supported baseline. Arch Linux itself is x86_64;
the ARM package is for compatible Arch Linux ARM installations.

Device sessions require **Python 3.10+ and ADB**. DEB/RPM/Arch packages declare
these dependencies; AppImage/tar users install them through their distro's package
manager (`python3` and `adb` on Debian/Ubuntu, `python3` and `android-tools` on
Fedora, `python` and `android-tools` on Arch). System GTK, NSS, GBM and audio
libraries must also be present; normal desktop installations usually have them.
ADB from `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or `~/Android/Sdk` is also detected.

Docker is optional for physical phones and existing emulators. The included
Android 16 Docker emulator needs **x86_64 Linux, Docker Engine with Compose, and
read/write `/dev/kvm` access**. ARM64 desktop builds can use physical devices and
an ADB server on another machine; the bundled Docker emulator is not an ARM VM.

## AppImage and application-menu installation

```bash
chmod +x Android-Agent-Lab-*.AppImage
./Android-Agent-Lab-*.AppImage
```

To install it for your user, download `install_appimage.py` from the same release:

```bash
python3 install_appimage.py ./Android-Agent-Lab-0.2.0-x86_64.AppImage
```

This creates a launcher and icon in your application menu, stores the image in
`~/.local/opt/android-agent-lab`, and adds `~/.local/bin/android-agent-lab`.
No root access is needed. Run the installer again with a newer image to update.
The image must be trusted: installation invokes its built-in icon extractor.

If FUSE is unavailable, run the image with `--appimage-extract-and-run`, or pass
`--extract-and-run` to the installer. This extracts the runtime on each launch,
which makes startup slower. On Ubuntu systems that restrict AppImage Chromium
user namespaces through AppArmor, prefer the DEB package, which installs the
app's sandbox profile. Do not disable the browser sandbox as a routine workaround.

## Use the shared screen

1. Open **Android Agent Lab** from the application menu.
2. Connect a USB-debugging-enabled phone, or choose **Start emulator**. Accept
   the phone's debugging authorization if needed, then **Refresh** devices.
3. Choose **Open device**. The app claims it and opens the interactive viewer.
4. Use **Copy browser URL** to open the same video in your browser or preview pane.
5. Use **Install coordination skill**, then **Copy agent instructions** and paste
   them into the Codex, Claude Code, or T3 thread you want to invite.

Use a unique actor label per agent for colored cursors. Commands share the same
claim and serialize through the coordinator. Human and agent inputs still change
one Android UI; take turns during assertions and gestures. The video path is
scrcpy H.264 with WebCodecs, without a VNC desktop in between. Input sends touch-down, movement, and release over the persistent scrcpy
control channel, with the shared lock held for the whole gesture. Holds, drags,
scrolling, navigation keys, and explicit Unicode clipboard paste are supported.

Choose **Agents only** or **Agents and user**. The human pointer is a small
circle that follows hover continuously; agent pointers have names and colors.
Toolbars beside the screen provide navigation, rotation, volume, screenshots,
recording, APK installation, Logcat, UI hierarchy, and settings shortcuts. Output
panels open below the device. See the [viewer guide](streaming.md) for limits.

**Already have a viewer?** Paste its private localhost URL at the bottom of the
launcher. This attaches another window to the existing stream. If a device is
claimed by a thread, **Join with owner's token** can start a new bridge with that
token; prefer the existing URL when there is already a running bridge.

Closing just the device window leaves its session and port running. **Stop
session** or quitting the launcher stops app-started bridges and releases claims
created by the app. Borrowed claims remain intact, as do externally started
viewers and the Docker emulator. To stop the emulator, release its claim and use
`python3 scripts/lab.py down` with `ADB_LAB_HOME` pointing at the app's `lab` directory,
or the corresponding source checkout. Its Docker volumes preserve app data.

Claims last one hour and renew on input, not passive viewing. Expiry or handoff
ends the old stream. An expired claim requires explicit **Reclaim expired session**.
Session tokens and URLs are kept in memory; they are copied only when you press
the corresponding button. Keep those clipboard contents private. A browser agent
can append `&actor=codex%3Athread-id` to the URL fragment for its cursor label.

## Local files and remote hosts

App settings and Docker configuration live under Electron's user data directory,
normally `~/.config/android-agent-lab`. The `.env` is preserved across upgrades.
Docker project name and volumes match the source launcher; do not run differently
configured copies of this same Compose project simultaneously.

The skill is copied into `skills/adb-coordination` under that directory so agents
have a stable path even with an AppImage. Installation links it into empty
`~/.codex/skills`, `~/.claude/skills`, and `~/.agents/skills` slots. Existing skills
are preserved. T3 uses its selected provider's discovery; refresh that provider's
session after installation. Copied session instructions include the exact helper
path, ADB endpoint, and claim-state directory.

The registry is shared with the CLI under
`${XDG_STATE_HOME:-~/.local/state}/adb-coordination`. Use `ADB_COORD_STATE`,
`ADB_SERVER_SOCKET`, and `ADB_COORD_ADB` consistently across all clients if you
override them. `ADB_LAB_PYTHON` selects Python for the desktop app. For a remote
ADB host, run coordination commands on that host under the same user and tunnel
the private viewer port over SSH. The app accepts localhost viewer URLs only.

## Build and verify

Build hosts need Node 22+, npm, Python 3.10+, `rpm`/`rpmbuild`, `bsdtar`
(`libarchive-tools` on Ubuntu), and `zstd`. The workflow builds natively on x86_64
and ARM64 runners; no application dependencies require native Node compilation.

```bash
npm ci --prefix desktop
npm run prepare-runtime --prefix desktop
npm test --prefix desktop
python3 -m unittest discover -s tests -v
npm start --prefix desktop
npm run build --prefix desktop -- --linux --x64
# On ARM64 use --arm64 instead of --x64.
```

Artifacts are in `desktop/dist`. `--smoke-test` launches a hidden app window,
checks renderer isolation, the preload interface, H.264 support, bundled Node,
and Python, prints JSON, and exits. Use a temporary `ADB_LAB_USER_DATA` directory
for automation. A GUI session or Xvfb is required. The smoke test does not
interact with Android devices.

`prepare_desktop.py` stages an explicit allowlist under `.desktop-build/runtime`;
it excludes `.lab`, `.env`, claims, APKs, and emulator data. The scrcpy server is
checksum verified and its upstream license is included, alongside Electron and
JavaScript dependency licenses. No Android system image is bundled in the desktop
download; Docker retrieves the emulator separately on first setup.

Release workflows attach installers and `SHA256SUMS`. The AUR, Homebrew tap,
Fedora COPR, and Ubuntu PPA have separate [distribution recipes](distribution.md).
These are community channels maintained by this project. There is no Flathub or
Snap Store submission. Package manager installations update through their package
manager; direct downloads are updated manually. No background updater is enabled.
