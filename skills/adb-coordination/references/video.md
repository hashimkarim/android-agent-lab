# Coordinated live video

For smoother browser viewing of an emulator or physical phone, use
[Android Agent Lab](https://github.com/Hashim-K/android-agent-lab)'s scrcpy/Tango
viewer. It requires that repository checkout, Node.js 22+, npm, Python 3.10+,
ADB, and a Chromium browser with WebCodecs. The standalone skill's
`scripts/adb_preview.py` is the dependency-light screenshot fallback.

Locate the user's lab checkout; do not assume this skill was installed inside
it. From that checkout, run setup once:

```bash
python3 scripts/video.py setup
```

Discover and claim the intended serial with this skill's coordinator first.
Reuse your thread's existing claim when it already owns that serial. For the
default Docker emulator, use `127.0.0.1:15555`; for USB or wireless devices, use
the actual serial from `adb_coord.py devices`. Then, from the lab checkout:

```bash
python3 scripts/video.py start --serial SERIAL --token TOKEN --control --port 8766 --duration 1800
```

Omit `--control` for observation and `--port` to choose a free port.
`ADB_COORD_TOKEN` can supply the token through the process environment. Open
the complete printed URL with the available preview tool. Keep its secret
fragment private and retain the exact supervisor PID for cleanup. If the
preview browser runs on another host, forward the same port over SSH.

The Android capture uses the official scrcpy server; the browser decodes the
video with WebCodecs. There is no need to open a desktop scrcpy window. The
browser controls send continuous touch-down/move/up through scrcpy, supporting
holds, drags, scrolling, navigation, and explicit Unicode clipboard paste.
Multitouch, full IME composition, audio, and automatic clipboard sync are not
implemented. Side toolbars provide APK installation, Logcat, UI hierarchy,
screenshots, recording, rotation, volume, and settings shortcuts. Agent actions
can use the normal coordinated ADB wrapper or browser controls. Use screenshots or Android UI hierarchy for native widget semantics;
the browser DOM only describes the viewer controls and canvas.

## Visible agent cursors

The updated coordinator emits named pointer feedback for direct
`shell input tap/swipe/text/keyevent` commands. The browser shows tap markers,
drag paths, and typing/navigation activity; it never receives typed characters
in these feedback events. Markers fade after eight seconds and turn red when
an input command fails. This is input feedback, not proof of an app response.

The default actor is the claim owner. When using a shared session, set
`ADB_COORD_ACTOR='codex:THREAD_ID'` (or `claude:`/`t3:`) in this thread's process,
or pass `--actor` to `adb_coord.py run` before `--`. Keep the valid claim token;
the actor only labels the cursor and does not grant ownership. Browser-driven
agents should append a URL-encoded actor to the existing private fragment,
for example `#key=...&actor=codex%3Athread-id`. Ordinary browser input defaults
to a human actor. Do not label agent automation as human input.

The cursor selector has **Agents only** and **Agents and user** modes. Human
pointers are small circles that follow hover continuously, before any click.
Browser agents also publish live hover positions; live pointers clear on leave
or disconnect. CLI feedback retains its eight-second lifetime.

The overlay is local to the browser and does not intercept clicks or add Android
commands. It is absent from native scrcpy and Android screenshots. Unwrapped
ADB and complex shell scripts do not emit these markers. Use native screenshots
or UI hierarchy to confirm the app's actual response.

## Ownership and cleanup

Every browser gesture holds the shared operation lock from down to up/cancel
and rechecks the token. Motion is sent directly to scrcpy without per-move
ADB processes or claim writes. Hover never sends Android input or renews a claim.
Passive video does not renew the claim. Humans and agents should take turns
when screen state matters. Handing off rotates the token and stops the old
viewer automatically; give the new token to the recipient and start a fresh
viewer. For a user session, hand off to `human:NAME` and leave its new viewer
running if requested. Report its bounded lifetime and stop command. Do not
release that claim while promising the preview will remain usable.

Ctrl+C or SIGTERM to the supervisor stops the streaming process without
shutting down the emulator or phone. Stopping the viewer leaves the claim
intact; release it when finished. A separately launched native scrcpy window
does not follow this lifecycle and must be closed explicitly before handoff.

Default video is H.264, longest edge 1280, up to 60 FPS; `--max-size 960` can
reduce encoding/decoding work. Higher `--max-fps` is a cap rather than a
guarantee. The full protocol, setup, limitations, and validation record are in
the lab's [streaming guide](https://github.com/Hashim-K/android-agent-lab/blob/main/docs/streaming.md).
