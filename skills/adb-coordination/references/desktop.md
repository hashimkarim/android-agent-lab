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

The viewer has **Agents only** and **Agents and user** cursor modes. The human
pointer is a small circle that tracks hovering continuously. Touch gestures
stream through scrcpy while holding the shared device lock until release or
cancel. Developer toolbars and output panels stay outside the phone screen.

The desktop app renews its one-hour claim on device input, not passive viewing.
Stopping or quitting releases app-created claims and stops their browser ports.
Joining with another thread's token leaves that thread's claim intact on exit.
Handoff rotates the token and ends old streams; restart the viewer explicitly.

Commands run on the ADB host under the same user and shared registry. Opening a
browser URL from a remote agent is not enough to share that host's file locks.
Use SSH/remote execution for ADB operations and an SSH tunnel for the preview.

**Install coordination skill** links the app's stable copy in its user data
directory into available Codex/Claude/Agents skill directories. Existing skills
are preserved. Prefer the exact path in copied session instructions because an
AppImage's mounted resources path changes between launches.

Installers and compatibility: https://github.com/Hashim-K/android-agent-lab/blob/main/docs/desktop.md
