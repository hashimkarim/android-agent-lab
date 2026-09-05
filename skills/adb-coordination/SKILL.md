---
name: adb-coordination
description: Coordinate live Android phones, tablets, and emulators across Codex, Claude Code, and T3 Code threads with shared ADB claims, serialized commands, previews, and handoffs. Use for USB or wireless device testing, Android deployment, ADB contention, and Docker emulator previews.
---

# ADB coordination

Give each Android device one cooperating thread at a time. Requires Python
3.10+, POSIX file locks, and ADB. Resolve `scripts/adb_coord.py` relative to this
skill's actual directory, including when loaded through a symlink.

For an interactive Docker emulator in a browser preview, read
[docker.md](references/docker.md). For existing devices, use the workflow below.
For live USB or wireless phones/tablets and the portable browser preview, read
[devices.md](references/devices.md). They use the same ownership protocol.
For direct scrcpy video and coordinated browser input on either kind of device,
including visible agent cursors, read [video.md](references/video.md).
For app creation, SDK setup, current Android documentation, and Studio features,
prefer [Google's Android CLI and skills](https://github.com/android/skills).
This skill adds ownership between threads; other tools must respect active
claims and do not automatically acquire the per-command lock.

## Discover, claim, and act

```bash
python3 /path/to/skill/scripts/adb_coord.py devices
python3 /path/to/skill/scripts/adb_coord.py status
python3 /path/to/skill/scripts/adb_coord.py claim --serial SERIAL --owner 'codex:unique-thread-id' --project /path/to/project --note 'Verify checkout'
```

Choose the intended available device, preferring a development emulator when
unspecified. An unauthorized/offline device is not a usable target. Use a unique
owner label for each thread, prefixed with its client (`codex:`, `claude:`, or
`t3:`); generate a UUID once if no session identifier is exposed.

Keep the returned token in this thread's context or process-local
`ADB_COORD_TOKEN`. Do not put it in source control, global instructions, shell
startup files, or shared handoff notes. Status omits tokens.

```bash
python3 /path/to/skill/scripts/adb_coord.py run --serial SERIAL --token TOKEN -- install -r /absolute/app-debug.apk
python3 /path/to/skill/scripts/adb_coord.py run --serial SERIAL --token TOKEN -- shell am start -W -n com.example.app/.MainActivity
python3 /path/to/skill/scripts/adb_coord.py screenshot --serial SERIAL --token TOKEN --out /tmp/new-screen.png
```

Build with the project's existing tools. Route device commands, including reads
during a test, through the wrapper. It pins the server and serial, and holds the
device lock across each command. A busy error means retry after that operation
finishes; do not delete lock files or bypass it with raw ADB. Bound long commands
with `--timeout` before `--`; prefer finite logcat capture.

Inspect screenshots before drawing UI conclusions. Browser DOM inspection sees
the viewer, not native Android widgets. Use screenshots and Android UI hierarchy
data for app semantics.

Claims default to 30 minutes and renew during commands. Renew before long builds
or pauses. Preserve app data and unrelated processes; normal installation does
not imply permission to uninstall, wipe data, or reset another thread's emulator.
Never use `adb kill-server` for routine contention recovery. The wrapper is not a
permission filter for arbitrary device shell commands.

## Handoff and recovery

```bash
python3 /path/to/skill/scripts/adb_coord.py renew --serial SERIAL --token TOKEN
python3 /path/to/skill/scripts/adb_coord.py release --serial SERIAL --token TOKEN
python3 /path/to/skill/scripts/adb_coord.py handoff --serial SERIAL --token TOKEN --owner 'claude:next-thread-id' --note 'Checkout open; next: empty-cart test'
```

Release when finished. Handoff rotates the token: give the new token to the
identified recipient through an already authorized mechanism, or a block the
user can paste. Include device serial, project/build, package/activity, current
screen, evidence paths, task-owned processes/ports, and next action. This skill
does not supply inter-thread messaging or synchronize conversation histories.

For an expired claim, inspect owner/note and ongoing device operations before
`claim ... --reclaim-expired`. The current owner may explicitly renew an expired
claim while its token still owns the record. A wrapped operation prevents
takeover even after its TTL expires. Device-side work may survive a killed ADB
client; inspect before recovery.

Stop only task-owned previews/emulators when finished, unless the user wants
them available. A Docker lab intended for interactive use can remain running;
report its URL and stop command. For a coordinated video session left for the
user, hand off to a human claim and start a new viewer with its token; releasing
the claim would stop that viewer. noVNC stays available without a claim.

## Client boundaries

All threads use the same host, user, state directory, and ADB endpoint. Default
state: `${XDG_STATE_HOME:-~/.local/state}/adb-coordination`; `ADB_COORD_STATE`
overrides it. Default server: `tcp:localhost:5037`; `ADB_SERVER_SOCKET` overrides
it. `ADB_COORD_ADB` selects the executable. Use a consistent serial spelling
(for the Docker lab, `127.0.0.1:15555` by default); aliases do not share claims.

See [clients.md](references/clients.md) for discovery and remote execution.
Claims are cooperative: raw ADB, Android Studio, scrcpy, and noVNC bypass them.
Humans and agents should take turns on the shared screen; the user can hold a
`human:NAME` claim to make cooperating agents wait. Separate emulators provide
independent UI state. Separate hosts/users do not share this local registry.
