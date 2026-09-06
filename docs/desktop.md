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
| Ubuntu 24.04; other Debian-based desktops meeting the dependencies | `.deb` | `sudo apt install ./Android-Agent-Lab-*.deb` |
| Fedora 43 / 44 | `.rpm` | `sudo dnf install ./Android-Agent-Lab-*.rpm` |
| Arch Linux; compatible Arch Linux ARM | `.pkg.tar.zst` | `sudo pacman -U ./Android-Agent-Lab-*.pkg.tar.zst` |
| Other glibc Linux desktops meeting the runtime requirements | `.AppImage` | Make executable, then launch it |
| Manual installations | `.tar.gz` | Extract and run `android-agent-lab` inside the directory |

Download only the package for your architecture. `x64`, `amd64`, and `x86_64`
mean 64-bit Intel/AMD; `arm64` and `aarch64` mean 64-bit ARM. These builds target
modern **glibc Linux** with X11 or Wayland. Alpine/musl, 32-bit machines, and old
Linux releases are outside the supported baseline. Arch Linux itself is x86_64;
the ARM package is for compatible Arch Linux ARM installations. Direct DEB builds
are installed and tested on Ubuntu 24.04 in both architectures; package-channel
checks also exercise Arch, Fedora 44 and Homebrew on Linux. Other derivatives
have not been individually tested. RPM dependencies use Fedora package names;
use the portable download on other RPM distributions unless you have checked
their compatibility.

### Verify your download

Download `SHA256SUMS` and your chosen installer from the **same release** into a
new directory. Run this there before installing or executing any downloaded file:

```bash
sha256sum --check --ignore-missing SHA256SUMS
```

Every file you downloaded must report `OK`; a mismatch is a failed verification.
The command also checks `install_appimage.py` when it is present. This verifies
the release's published checksums; no detached release signature is provided.

Keep only the installer for your chosen format and architecture in that directory
when using the wildcard install commands above. Check `uname -m` if unsure.

Device sessions require **Python 3.10+ and ADB**. DEB/RPM/Arch packages declare
these dependencies; AppImage/tar users install them through their distro's package
manager (`python3` and `adb` on Debian/Ubuntu, `python3` and `android-tools` on
Fedora, `python` and `android-tools` on Arch). System GTK, NSS, GBM and audio
libraries must also be present; normal desktop installations usually have them.
ADB from `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or `~/Android/Sdk` is also detected.
QR pairing needs working mDNS discovery. If the selected ADB build has no mDNS
support, the app uses the system's Avahi service. Native packages include the
Avahi client; AppImage/tar users can install `avahi-utils` on Debian/Ubuntu,
`avahi-tools` on Fedora, or `avahi` on Arch and enable their distro's Avahi service.
Pairing-code and manual IP/port entry remain available without mDNS.
On the supported systemd distributions, start that service with
`sudo systemctl enable --now avahi-daemon.service` if Avahi discovery is unavailable.

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
python3 install_appimage.py ./Android-Agent-Lab-0.3.1-x86_64.AppImage
```

This creates a launcher and icon in your application menu, stores the image in
`~/.local/opt/android-agent-lab`, and adds `~/.local/bin/android-agent-lab`.
No root access is needed. Run the installer again with a newer image to update.
The image must be trusted: installation invokes its built-in icon extractor.
Use the `arm64.AppImage` asset on ARM64. If `android-agent-lab` is not found, add
`export PATH="$HOME/.local/bin:$PATH"` to your shell configuration and open a
new terminal, or run `~/.local/bin/android-agent-lab` directly.

If FUSE is unavailable, run the image with `--appimage-extract-and-run`, or pass
`--extract-and-run` to the installer. This extracts the runtime on each launch,
which makes startup slower. On Ubuntu systems that restrict AppImage Chromium
user namespaces through AppArmor, prefer the DEB package, which installs the
app's sandbox profile. Do not disable the browser sandbox as a routine workaround.

## Portable tar archive

Verify the `.tar.gz` download, extract it into a dedicated directory, and run
the launcher inside that directory. For the x86_64 release:

```bash
mkdir -p "$HOME/.local/opt/android-agent-lab-0.3.1"
tar -xzf Android-Agent-Lab-0.3.1-x64.tar.gz --strip-components=1 -C "$HOME/.local/opt/android-agent-lab-0.3.1"
env -u ELECTRON_RUN_AS_NODE "$HOME/.local/opt/android-agent-lab-0.3.1/android-agent-lab" --version
env -u ELECTRON_RUN_AS_NODE "$HOME/.local/opt/android-agent-lab-0.3.1/android-agent-lab"
```

On ARM64, choose the `arm64.tar.gz` asset instead. Keep the extracted runtime
together; copying the executable alone omits its required resources. The tar
archive does not add a menu entry or a global command. Prefer the AppImage
installer or a native package for that integration.

## Upgrade and remove portable installs

Quit the launcher before replacing its runtime. Use **Stop** on any emulator
you also want to shut down; its apps and data remain on disk. For an AppImage
installed with `install_appimage.py`, verify the newer image and installer and
run the installer again. For a directly launched AppImage, replace the image;
for a tar install, extract the new version into a new directory before removing
the old runtime directory. There is no background updater.

To remove only an AppImage installation made with the supplied installer:

```bash
rm -f -- "$HOME/.local/bin/android-agent-lab" \
  "$HOME/.local/opt/android-agent-lab/Android-Agent-Lab.AppImage" \
  "${XDG_DATA_HOME:-$HOME/.local/share}/applications/android-agent-lab.desktop" \
  "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps/android-agent-lab.png"
rmdir -- "$HOME/.local/opt/android-agent-lab"
```

The final command removes the directory only if it is empty. For direct AppImage
or tar use, remove the downloaded image or dedicated extracted runtime directory
and any launcher you created. These steps leave your workspace, saved APKs,
project repositories, claims and Android data intact. For native packages and
repository removal, use the [package manager instructions](distribution.md#upgrade-and-uninstall).

## Open a project from the terminal

```bash
android-agent-lab .
android-agent-lab "/home/you/projects/My Android App"
android-agent-lab --project ../my-app
android-agent-lab --help
```

Pass the Gradle root containing `gradlew`. The app adds it to **Projects & APKs**
and selects its card, bringing the existing window forward when already running.
Relative paths use the calling terminal's directory. Reopening a saved path or a
symlink to it keeps the same entry and its build settings. Use **Edit settings**
to choose a task, application ID and APK output. Opening does not execute Gradle.

A first launch stays attached to the terminal; append `&` or use your agent's
background process support to keep using that terminal. Restart an older running
version after updating so it can handle project paths. Invalid paths and options
print an error with a nonzero exit code. Use `--` before a path starting with a
dash. The command accepts one project per invocation; no argument opens the app.

The AppImage installer puts the command in `~/.local/bin`; add that directory to
PATH or invoke `~/.local/bin/android-agent-lab` directly. DEB, RPM, Arch and
Homebrew installations provide the same executable name. From source, use
`node /path/to/android-agent-lab/desktop/start.cjs /absolute/project/path`.

**Install agent skills** installs both `android-agent-lab-projects` for this
workflow and `adb-coordination` for live device sessions. Agents can use the
project skill automatically or explicitly as `$android-agent-lab-projects`.

## Use the shared screen

1. Open **Android Agent Lab** from the application menu.
2. Use **Add phone** for wireless pairing, plug in a USB phone, or add and start
   an emulator. USB devices refresh automatically; accept the phone’s debugging prompt.
3. Choose **Open device**. The app claims it and opens the interactive viewer.
4. Use **Copy browser URL** to open the same video in your browser or preview pane.
5. Use **Install agent skills**, then **Copy agent instructions** and paste
   them into the Codex, Claude Code, or T3 thread you want to invite.

Use a unique actor label per agent for colored cursors. Commands share the same
claim and serialize through the coordinator. Human and agent inputs still change
one Android UI; take turns during assertions and gestures. The video path is
scrcpy H.264 with WebCodecs, without a VNC desktop in between. Input sends touch-down, movement, and release over the persistent scrcpy
control channel, with the shared lock held for the whole gesture. Holds, drags,
scrolling, navigation keys, and explicit Unicode clipboard paste are supported.

Choose **No cursors**, **Agents only**, or **Agents and user**. The human pointer is a small
circle that follows hover continuously; agent pointers have names and colors.
Toolbars beside the screen provide navigation, rotation, volume, screenshots,
recording, APK installation, Logcat, UI hierarchy, and settings shortcuts. Output
panels open below the device. See the [viewer guide](streaming.md) for limits.

**Install APK** opens your project and APK library first. Choose an existing
project output or saved APK, or use **Build & install**. The target is the device
in this live view; the desktop's Jobs page shows output and cancellation. A
project with ABI-specific APKs from one variant automatically selects the device's
preferred CPU architecture. Multiple app variants need a task/output override,
or you can select an existing output in the picker. **Browse files…** opens the
normal file picker for an APK on the browser's computer. Standalone viewers
without a desktop session offer this file picker too.

No cursors keeps the system pointer visible and disables cursor overlays, their
animation and resize work, and hover-only network updates. Touch and drag input
continues directly through scrcpy.

Under **Viewing & agent settings**, paste an existing private localhost viewer URL. This attaches another window to the existing stream. If a device is
claimed by a thread, **Join with owner's token** can start a new bridge with that
token; prefer the existing URL when there is already a running bridge.

Closing just the device window leaves its session and port running. **Stop
session** or quitting the launcher stops app-started bridges and releases claims
created by the app. Borrowed claims remain intact, as do externally started
viewers and Android data. Use an emulator card's **Stop** to turn it off while
keeping apps and data, or **Delete** to remove that instance and its Android
volumes. Close its shared session first. Deletion requires confirmation in the app.

Claims last one hour and renew on input, not passive viewing. Expiry or handoff
ends the old stream. An expired claim requires an explicit reclaim before opening a new session.
Ordinary session tokens and URLs are kept in memory; they are copied only when you press
the corresponding button. Keep those clipboard contents private. A browser agent
can append `&actor=codex%3Athread-id` to the URL fragment for its cursor label.

## Phones, multiple emulators, and locks

**Add phone → Scan QR** uses Android 11+ Wireless debugging. Put the phone and
computer on the same network, then scan from **Developer options → Wireless
debugging → Pair device with QR code**. Codes expire after three minutes. The
**Pairing code** tab discovers nearby pairing services using ADB or Avahi.
IP address and port have separate fields. The app offers your laptop's LAN
prefix, lets you choose between Wi-Fi/Ethernet interfaces, and selects the last
IPv4 number when you focus the address. The entire IP remains editable; pasting
an IP:port fills both fields. Manual entry works without multicast discovery.
After pairing, the app tries the matching device's advertised connection ports,
including alternatives when an old port is stale. If it cannot connect, it keeps
the successful pairing and opens the connection-port form with the IP filled in.
The pairing port and connection port are different. USB discovery does not require
Wi-Fi; use a data cable and accept the debugging prompt on the phone.

For a paired phone or Wear OS watch that is missing or offline, keep Wireless
debugging open and use the IP and connection port on its main screen. Both can
change when the device changes network or wireless debugging restarts. Use
**Update connection…** on an offline wireless device, or **Add phone → Pairing
code → Already paired, but not connected?**. A paired device still needs an ADB
connection before video can start. Startup errors distinguish an unavailable
ADB transport from a display query that stopped responding. See the official
[Wear OS connection steps](https://developer.android.com/training/wearables/get-started/debug-wifi).

**Rename** saves a display name locally. It does not change the phone's system
name, ADB serial or Android hostname. A phone exposed through USB and Wi-Fi has
two transport serials; choose one for coordinated work rather than treating them
as independent phones.

Create as many emulator entries as the host can support. Each gets unique local
ports, a Compose project and persistent Android volumes. The previous desktop
emulator is adopted without moving or resetting its data. Each running instance
can use up to 6 GB of memory; emulator creation itself does not download or boot
Android. Canceling startup cancels the job; a container already started can stay
running until you press **Stop**.

**Lock for me** keeps a device reserved across app restarts and while Android is
stopped. Locking and unlocking invalidate old agent tokens and browser URLs. The
human viewer reopens with fresh access, and agent invitations are disabled while
locked. Unlock to share fresh instructions. Locks cover cooperating agents using
the shared coordinator; they cannot block raw ADB, Android Studio, other users,
or an alias serial. Do not delete claim files to bypass a reservation.

## Saved projects and APKs

In **Projects & APKs**, select a Gradle project root containing `gradlew`.
**Detect settings** reads app modules, the debug task, literal application IDs,
Gradle/AGP versions and existing APK variant metadata. Java and SDK paths appear
in the same dialog. Blank overrides follow the repository again on each build;
custom task, application ID, APK, JDK and SDK fields remain available. Detection
does not execute the wrapper. Computed Gradle logic and custom flavors may need
an explicit task or a first build to produce reliable APK metadata.

Builds select an installed JDK compatible with the wrapper and Android plugin,
even if the app inherited an older `JAVA_HOME`. Gradle Java-home settings and
daemon JVM version criteria are checked; an explicit JDK override applies only
to that job. SDK discovery checks `local.properties`, environment variables and
standard installation directories. A repository's `sdk.dir` takes precedence;
conflicting or unavailable paths are explained before Gradle starts. Nothing
changes the system's Java selection or the repository's configuration files.
See [Gradle's Java compatibility table](https://docs.gradle.org/current/userguide/compatibility.html#java_runtime)
and [Android's JDK guidance](https://developer.android.com/build/jdks).

**Jobs** provides live output, **Copy output** (including the result message),
**Remove** for a finished job and **Clear finished** for completed, failed and
cancelled entries. Running jobs remain visible until they finish or are cancelled.
Removing history keeps generated APKs, projects and Android data.

**Build** copies generated APKs into the library. **Build & install** requires a
single unambiguous APK and a selected connected device. Standalone ABI-specific
APKs from one app variant are selected using the device's preferred CPU
architecture. Specify a task/output for multiple app variants. Split APK sets
requiring multiple files are not installed automatically. **Save APK** also stores a private copy, so later edits
or removal of the original do not change the saved artifact. Removing library
entries keeps original APKs and project directories.

**Launch**, **Debug launch**, and **App logs** use the saved application ID and
selected device. Debug launch starts the app waiting for a Java/Kotlin debugger;
attach from Android Studio or a debugger on the ADB host. App logs capture a
bounded snapshot for the running app. This is not an embedded source debugger.
Device jobs share existing desktop claims, use a human reservation, or acquire
and release a temporary claim. They do not take another agent's claim.

## Latency settings

Choose a preset under **Viewing & agent settings** before opening a new session:
**Fast** (960 px, 60 FPS, 3 Mbps), **Balanced** (1280 px, 60 FPS, 6 Mbps), or
**Detail** (1920 px, 60 FPS, 10 Mbps). Fast is the desktop default. The viewer draws
VideoFrames directly, resizes its canvas only when dimensions change, bounds
pending encoded packets, and coalesces obsolete pointer moves. There is no
intentional video delay. Cursor drawing stays outside Android capture.

Viewer statistics show actual displayed FPS, control acknowledgement time and
pending/dropped packets. Acknowledgement time measures delivery to the scrcpy
control stream, **not** motion-to-display latency. FPS can drop to zero on a still
screen. Device rendering, software emulator graphics, encoding, Wi-Fi and host
load still contribute latency; USB and the Fast preset reduce avoidable work.

## Local files and remote hosts

App settings live under Electron's user data directory, normally
`~/.config/android-agent-lab`. `workspace.json` stores names, projects, APK metadata
and private human reservation tokens with owner-only permissions. `apks/` holds
library copies; `emulators/ID/` holds each new instance's Docker configuration.
The original `lab/.env` and default Compose project are preserved across upgrades.
Never share the workspace file as agent instructions or check it into Git.

The bundled skills are copied into `skills/adb-coordination` and
`skills/android-agent-lab-projects` under that directory so agents have stable
paths even with an AppImage. Installation links them into empty
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
git clone https://github.com/Hashim-K/android-agent-lab.git
cd android-agent-lab
npm ci --prefix desktop
npm run prepare-runtime --prefix desktop
npm test --prefix desktop
npm run test:ui --prefix desktop # desktop session or xvfb-run; isolated simulated ADB
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
