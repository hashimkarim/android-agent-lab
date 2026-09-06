Android Agent Lab 0.3.1 adds a persistent workspace for phones, emulators, projects
and APKs.

- Pair Android 11+ phones over Wi-Fi with QR codes, nearby mDNS discovery, or a
  pairing code. USB devices refresh automatically with authorization guidance.
  Avahi supplies discovery when distro ADB builds lack mDNS. Its resolver gets
  time to finish and flush results, avoiding intermittent empty nearby scans.
  Separate IP and port fields offer the laptop's LAN prefix and easy last-number editing. Pairing
  connects the matching advertised device automatically, with manual connection
  guidance and address updates for offline phones and watches.
- Create multiple Android 16 emulators with separate ports and Android data.
  Rename, start, stop or delete individual instances. Existing emulator data is
  adopted without resetting it.
- **Lock for me** reserves devices across app restarts and revokes previous
  agent tokens and viewers. Unlock to share fresh access. Locks coordinate
  cooperating agents using the same host registry; raw ADB remains outside it.
- Open or register a project with `android-agent-lab .` or a directory path.
  Reopening preserves saved build settings and selects the project in the running
  app. The bundled `android-agent-lab-projects` skill supports agent workflows.
- Save APK copies and Gradle projects with build tasks, output paths and app IDs.
  Build, install, launch, start waiting for a debugger, or capture app logs.
  Detect app modules, debug tasks, application IDs, variant outputs and installed
  JDK/SDK paths from the repository and AGP output metadata. Each build selects a
  compatible installed JDK, fixing desktop launches that inherit old Java versions.
  Keep optional overrides for custom build logic, flavors and toolchain paths.
  ABI-specific APKs from one variant are matched to the target device automatically.
  Background jobs provide **Copy output**, **Remove**, **Clear finished** and
  cancellation. Running jobs cannot be removed; failure notices use error styling.
  **Install APK** in a live view opens the project/APK library first, with
  existing output selection, Build & install, and a filesystem picker alternative.
- **No cursors** keeps the system pointer and disables cursor overlays, overlay
  animation and hover-only traffic. It joins Agents only and Agents and user.
  Fast/Balanced/Detail
  stream presets, direct VideoFrame rendering, fewer canvas resets, bounded
  packet work and coalesced pointer moves reduce avoidable viewing delay.
- Viewer statistics show control ACK timing and queue state. ACK timing is not
  motion-to-display latency; device encoding and software emulator graphics
  still affect responsiveness.

Validation includes helper and transport tests, automated Electron UI flows with
real WebCodecs decoding, project and APK jobs, cursor modes, shared locks and
token revocation. Discovery fallback was verified with distro ADB and Avahi;
a paired Xiaomi was connected successfully. QR rendering and pairing flows are
tested; scanning with a physical phone still needs device-side verification.
OmegaVR's Gradle 9.6.1 debug build passed with automatically selected Java 17 and
the local Android SDK.

AppImage, DEB, RPM, Arch and tar builds support x86_64 and ARM64 glibc Linux.
Python 3.10+ and ADB are required. Local Docker emulators additionally require
x86_64, Docker Compose and KVM.
