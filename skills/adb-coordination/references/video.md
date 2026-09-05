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
browser controls support taps, swipes sent on release, navigation keys, and
printable ASCII text. Advanced gestures, Unicode/IME, audio, and clipboard sync
are not implemented. Agent actions still use the normal coordinated ADB
wrapper. Use screenshots or Android UI hierarchy for native widget semantics;
the browser DOM only describes the viewer controls and canvas.

Every browser input takes the shared operation lock and rechecks the token.
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

Default video is H.264, longest edge 1280, up to 30 FPS; `--max-size 960` can
reduce encoding/decoding work. Higher `--max-fps` is a cap rather than a
guarantee. The full protocol, setup, limitations, and validation record are in
the lab's [streaming guide](https://github.com/Hashim-K/android-agent-lab/blob/main/docs/streaming.md).
