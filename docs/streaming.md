# Browser video and native scrcpy

The browser viewer uses the **official scrcpy Android server**,
[Tango's ADB/scrcpy client](https://tangoadb.dev/scrcpy/), and its
[WebCodecs decoder](https://tangoadb.dev/scrcpy/video/web-codecs/).
It captures Android directly and decodes H.264 in the browser. A desktop scrcpy
window is optional; there is no desktop-window capture or VNC in this path.
The same viewer works with the Docker emulator and connected physical devices.

## Start the browser viewer

Requires the repository checkout, Python 3.10+, Node.js 22+, npm, ADB, and a
current Chromium browser with WebCodecs. Docker/KVM is needed only for the
container emulator. From the checkout:

```bash
python3 scripts/video.py setup
python3 skills/adb-coordination/scripts/adb_coord.py devices
python3 skills/adb-coordination/scripts/adb_coord.py claim --serial SERIAL --owner 'human:your-name' --project "$PWD" --note 'Interactive browser session'
python3 scripts/video.py start --serial SERIAL --token TOKEN --control --port 8766
```

Replace `SERIAL` with the exact device serial and `TOKEN` with the returned claim
token. For the default Docker emulator use `127.0.0.1:15555` after `lab.py up`.
If your thread already owns the device, reuse its token; do not claim again.
`ADB_COORD_TOKEN` in the process environment can replace `--token TOKEN`.

Open the complete printed private URL in the browser or preview pane. It
contains an access key in its fragment. Keep both access keys and claim tokens
out of commits. Without `--control`, the viewer is read-only. Omitting `--port`
selects an available loopback port. For a remote device host, forward the same
port over SSH, for example `ssh -L 8766:127.0.0.1:8766 DEVICE_HOST`.

The setup command installs locked npm dependencies, builds the frontend, and
downloads the official scrcpy server **3.3.3** with a pinned SHA-256. That server
version matches the published Tango adapter used here. A separately installed
desktop scrcpy can be newer; do not substitute its server binary without
updating and testing the matching client protocol.

## Interaction and handoff

Click, hold, drag, scroll, and type directly on the screen. Touch-down, movement,
and release travel over a persistent scrcpy control channel; the app responds
while you are dragging. Click the screen for keyboard input, or use **Paste to
device** for Unicode text via the Android clipboard. Clipboard contents are sent
only when you explicitly paste. Automatic clipboard synchronization, audio,
multitouch, and full IME composition are not implemented.

Toolbars sit outside the phone screen in both the desktop app and browser:

- Power, volume, rotation, Back, Home, Recents, notifications, and quick settings.
- Full-resolution PNG screenshots and WebM screen recording (video only,
  up to five minutes / approximately 128 MB; cursor overlays are excluded).
- APK installation, the latest 500 Logcat lines, UI hierarchy inspection, and
  shortcuts to Android settings, developer options, and app management.
- Fit, zoom, fullscreen, and video refresh. Tool output opens below the screen
  with refresh and save controls. APK uploads are limited to 200 MB.

The Rotate button locks Android to portrait or landscape; **Auto-rotate**
restores sensor rotation. Coordinates follow the streamed frame dimensions. A rotation during an active
gesture cancels that gesture. Restart after changing the device's display
resolution outside the viewer.

### Agent cursors

The **Cursors** selector has two modes, saved locally in each viewer:

- **Agents only** shows named, colored agent pointers.
- **Agents and user** also shows the human pointer as a small circle, with a
  larger pressed state. It follows hover and drag continuously, before any
  click, and disappears when the pointer leaves the screen.

Browser agents also publish continuous hover positions. Live pointers stay
visible while present and clear on disconnect. Coordinated CLI taps and swipe
paths remain visible for eight seconds; failed actions turn red. Typing and
navigation appear in the activity line without exposing typed characters.
Cursor feedback does not prove that the app handled an action.

Agent commands through `lab.py adb` or the updated `adb_coord.py run` emit this
feedback automatically, using the claim owner's label. To identify an agent
working in a shared session, keep the valid token and set its display actor:

```bash
python3 skills/adb-coordination/scripts/adb_coord.py run --serial SERIAL --token TOKEN --actor 'codex:thread-id' -- shell input tap 500 800
ADB_COORD_ACTOR='claude:thread-id' python3 scripts/lab.py adb --token TOKEN -- shell input swipe 500 1200 500 400 300
```

Browser input gets a human label by default. For an agent driving the browser,
append `&actor=codex%3Athread-id` to the private URL's existing `#key=...`
fragment. The actor is a display label; it does not change ownership or grant
access. Distinct thread labels retain distinct pointers. All viewers still
operate the same Android screen.

The cursor layer runs in the browser, independently of the video canvas. It
adds no Android commands or video re-encoding and pauses drawing while markers
are stationary. It remains outside native scrcpy, noVNC, and Android screenshots.
A native overlay is deferred pending performance validation. Raw ADB, native
scrcpy input, and complex shell scripts that bypass the coordinator do not
produce these named markers. Direct `shell input tap/swipe/text/keyevent`
commands are recognized; a cursor is not guessed for other shell commands.

### Shared input and lifecycle

The video connection observes the active claim without extending its lifetime.
The persistent Python broker takes the same per-device lock used by agent ADB
commands. A touch gesture holds it from down through up/cancel; movement goes
directly to scrcpy without spawning ADB/Python processes or saving claims for
each move. Navigation, text, and developer tools also take the shared lock.
Inputs renew ownership, while hover only updates visual presence. Disconnect,
window blur, rotation, and idle/hard timeouts cancel held touches and release
the operation lock. Humans and agents operate the same Android screen and
should take turns during tests that need stable screen state.

Release, expiry, or token rotation closes the old stream and listener; browser
input rechecks ownership inside the operation lock. To switch owners:

```bash
python3 skills/adb-coordination/scripts/adb_coord.py handoff --serial SERIAL --token TOKEN --owner 'codex:next-thread-id' --note 'Current app and next test'
```

Give the new token only to the intended recipient, then start a new viewer
with it. The old URL is revoked. A viewer lasts 30 minutes by default;
`--duration SECONDS` sets a limit up to 24 hours, independently of claim expiry.
Ctrl+C or SIGTERM stops the viewer and its streaming child. Stopping a viewer
does not release the claim or stop the emulator/phone. Release the claim when
finished. Unwrapped ADB, native scrcpy, Android Studio, and noVNC still bypass
the cooperative ownership protocol.

The loopback bridge exposes the selected device's video and bounded input API,
not the host's general ADB server. HTTP and WebSocket requests check the access
key and local Host/Origin. This is a local development tool, not a multi-user
device service; users sharing the host account can access its processes/state.

## Performance and alternatives

The defaults are H.264 at up to 1280 pixels on the longest edge, 60 FPS, and
4 Mbit/s. Try `--max-size 960` if decoding or encoding is expensive, or
`--max-fps 30` to reduce work. FPS is a maximum, not a promised frame rate;
static screens may produce no new frames. Reconnect reloads the viewer and
replays a bounded cached keyframe group so a static app can appear immediately.

| Viewer | Useful for | Tradeoff |
| --- | --- | --- |
| Browser scrcpy, included | Direct Android video in the preview pane with coordinated input | WebCodecs required; single-pointer touch and explicit clipboard paste |
| Native scrcpy | Desktop mirroring and mature keyboard/gesture handling | Separate window; does not enforce this lab's claims |
| noVNC, included with Docker | Emulator toolbar, rotation, and extended emulator controls | Captures the container desktop through an additional display path |
| Portable screenshot viewer, included in the skill | Inspecting a phone without the Node bridge | About one update per second |

Native scrcpy can target the same device:

```bash
scrcpy --serial SERIAL --max-size=1280 --max-fps=60 --video-bit-rate=4M --no-audio
```

Add `--no-control` for observation, respect the claim and ADB server endpoint,
and close that exact process before releasing or handing off. The browser and
native window see the same device state; running both can add encoding work.
See [scrcpy's video options](https://github.com/Genymobile/scrcpy/blob/master/doc/video.md).

Actual latency depends on Android rendering, encoding, buffering, and browser
decoding. The Docker emulator uses software graphics. Direct capture removes
the VNC desktop path but does not accelerate Android itself; this release has
no controlled end-to-end latency benchmark.

The input architecture follows upstream scrcpy's continuous control channel.
[Sefirah's mirroring service](https://github.com/shrimqy/Sefirah/blob/master/src/Sefirah/Services/ScreenMirrorService.cs)
also launches upstream scrcpy. Its application code was not copied; this
project keeps Tango for the shared browser/desktop transport.

### Control API

Agents can keep using coordinated ADB commands or drive the browser. For a
persistent client, connect to `/control` with WebSocket subprotocol
`adb-control.KEY`, using the private viewer key. Include a unique `actor` and
optional request `id` (for acknowledgements). Pointer/hover coordinates use the
**encoded frame width and height**, not Android's physical pixel dimensions:

```json
{"kind":"hover","actor":"codex:thread-id","x":200,"y":400,"width":568,"height":1280}
{"kind":"pointer","phase":"down","actor":"codex:thread-id","id":1,"x":200,"y":400,"width":568,"height":1280}
{"kind":"pointer","phase":"move","actor":"codex:thread-id","x":200,"y":300,"width":568,"height":1280}
{"kind":"pointer","phase":"up","actor":"codex:thread-id","id":2,"x":200,"y":300,"width":568,"height":1280}
```

Hover with `phase:"leave"` clears presence. Use the same socket/actor for the
entire gesture. Stale dimensions and competing gestures are rejected. The
existing authenticated `POST /input` tap/swipe/key/text interface remains
available; tap/swipe coordinates there remain physical Android pixels.

## Verification record

On 2026-09-05, the browser viewer decoded live 568 × 1280 H.264 video from the
Android 16 / API 36.1 Docker emulator. Chromium browser clicks incremented a
native test app's counter, and browser text input appeared in its Android UI
hierarchy. Reloading decoded the cached stream without requiring an app action.
The T3 preview browser also decoded the stream. Live checks confirmed that
claim handoff revoked old-token input and closed the active stream/listener;
read-only mode rejected input, and SIGTERM/SIGKILL cleanup left no Android
scrcpy server process. HTTP access-key, Host, and Origin checks also passed. Physical-device video uses the
same explicit-serial path but has not been exercised on a phone in this release.

Cursor validation used two browser clients connected to the same emulator:
coordinated CLI input and browser input produced separate actor labels at the
correct screen coordinates. Drag feedback, click-through behavior, resize,
visibility toggling, and expiry passed without browser errors. Automated tests
also cover attribution, rejected claims, failed input, handoff isolation,
bounded feedback storage, and omission of typed text.

Additional live validation for continuous input used an Android test view:
MOVE events changed its rendered screen while the browser mouse remained down,
and a competing coordinated ADB command was rejected until release. Two viewers
verified hover-only human circles, named agent hover, mode filtering, and cursor
cleanup. APK upload, Logcat, hierarchy, PNG downloads, WebM recording, fullscreen,
and non-overlapping layouts at 430/680/980 pixels passed. Unit tests exercise
gesture serialization, disconnect cancellation, read-only/stale-claim rejection,
clipboard attribution, and broker EOF cleanup.

The project reuses upstream capture and decoding instead of maintaining a
scrcpy fork. [NetrisTV/ws-scrcpy](https://github.com/NetrisTV/ws-scrcpy) offers
another browser UI, but its README documents a modified scrcpy 1.19 server
(reviewed 2026-09-05). Tango lets this bridge use an official newer server.

### Workspace release latency changes

The desktop defaults to the Fast preset (960 px / 60 FPS / 3 Mbps). CLI users can
pass `--profile fast`, `--profile balanced`, or `--profile detail` to `video.py
start`. A profile overrides `--max-size`, `--max-fps`, and `--bit-rate`. The viewer
avoids per-frame canvas resets, draws VideoFrames directly, bounds packet work,
and coalesces pending pointer moves without losing down/up/cancel boundaries.
**No cursors** keeps the native system pointer and disables the overlay,
its animation/resize work, and hover-only network traffic. Actual touches and
drags continue directly over scrcpy. Control ACK timing in the toolbar is not
an end-to-end latency measurement.

In a live desktop session, **Install APK** opens saved projects and APKs before
offering **Browse files…**. Select an existing output, install a saved copy, or
build and install a project on that same device. Library operations use the
desktop job queue and recheck its current device token. A standalone viewer
without a desktop library still supports the filesystem APK picker.
