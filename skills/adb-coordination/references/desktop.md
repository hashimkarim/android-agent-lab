# Shared desktop sessions

Android Agent Lab's Linux app and browser preview display the same scrcpy stream.
Use **Copy agent instructions** on its session card. That supplies the exact
coordinator path, serial, ADB endpoint, state directory, token, and browser URL.
Use that token with a unique `ADB_COORD_ACTOR` such as `codex:THREAD-ID` or
`claude:THREAD-ID`; actions then show named cursors in both desktop and browser.

The human has invited the agent into this session. Do not claim the device
again or release the shared claim when your own task finishes. Leave it for the
human. Each command still takes the per-device lock, and both sides should take
turns when a test needs a stable screen. Status alone never reveals the token.

The viewer has **No cursors**, **Agents only**, and **Agents and user** modes. The human
pointer is a small circle that tracks hovering continuously. Touch gestures
stream through scrcpy while holding the shared device lock until release or
cancel. Developer toolbars and output panels stay outside the phone screen.

No cursors keeps the system pointer visible and disables cursor overlays, their
animation and resize work, and hover-only network updates. Touch and drag input
continues directly through scrcpy.

The desktop app renews an ordinary one-hour claim on device input, not passive viewing.
Stopping or quitting releases app-created claims and stops their browser ports.
Joining with another thread's token leaves that thread's claim intact on exit.
Handoff rotates the token and ends old streams; restart the viewer explicitly.

**Lock for me** is a persistent human reservation, including while an emulator
is stopped. Locking or unlocking rotates the token and revokes old viewers and
agent instructions. Never recover its token from app files or override its
claim. The human can unlock it and copy a fresh invitation. These reservations
coordinate participating clients; raw ADB and Android Studio remain outside the
protocol. USB and Wi-Fi aliases of a phone still need one canonical serial.

Each managed emulator has its own Compose project, ADB port and Android volumes.
Read the actual serial from the session invitation; do not assume port 15555.
Use the desktop's **Stop** to preserve data and **Delete** only when that data
deletion is authorized. Stop the shared session before changing its container.

The desktop can save APK copies and Gradle project paths, tasks and APK outputs.
Builds use the host JDK/SDK; installation uses the selected device claim. Do not
start a second install or control gesture while a desktop device job holds the
lock. **Debug launch** waits for an external Java/Kotlin debugger; it is not an
embedded IDE debugger.

**Install APK** in a live viewer opens saved projects and APKs first. Choose an
existing APK or **Build & install** for that viewer's device; the desktop Jobs
page shows output and cancellation. **Browse files…** selects an APK on the
browser host. The picker rechecks the shared session token before starting work.

Commands run on the ADB host under the same user and shared registry. Opening a
browser URL from a remote agent is not enough to share that host's file locks.
Use SSH/remote execution for ADB operations and an SSH tunnel for the preview.

To save or reopen a local Gradle project in the app, run
`android-agent-lab /absolute/project/path` (or `android-agent-lab .` in its root).
The root must contain `gradlew`; reopening keeps existing build settings. This
only registers and selects the project. The companion `android-agent-lab-projects`
skill covers the command; adding a project needs no device claim.

**Install agent skills** links the app's stable skill copies in its user data
directory into available Codex/Claude/Agents skill directories. Existing skills
are preserved. Prefer the exact path in copied session instructions because an
AppImage's mounted resources path changes between launches.

Installers and compatibility: https://github.com/Hashim-K/android-agent-lab/blob/main/docs/desktop.md
