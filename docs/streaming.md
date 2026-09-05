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

Click for a tap, drag for a swipe, and use Back/Home/Recents above the screen.
Click the screen before typing, or use the text box to send a string. Current
input supports printable ASCII, navigation keys, and single-pointer gestures.
Swipes are sent on release with a fixed 300 ms duration. Multitouch, long press,
audio, clipboard sync, arbitrary Unicode/IME input, and the literal sequence
`%s` in text are not implemented. Restart the viewer after changing Android's
display resolution. Rotation is mapped from the streamed frame orientation.

The video connection observes the active claim without extending its lifetime.
Every browser input goes through the Python coordinator's per-device lock and
renews the claim, just like agent ADB commands. This keeps ownership checks
consistent; input currently uses ADB injection and can feel slower than native
scrcpy's continuous control channel. Humans and agents can both operate the
same app, but should take turns during tests that need stable screen state.

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

The defaults are H.264 at up to 1280 pixels on the longest edge, 30 FPS, and
4 Mbit/s. Try `--max-size 960` if decoding or encoding is expensive, or
`--max-fps 60` for a higher cap. FPS is a maximum, not a promised frame rate;
static screens may produce no new frames. Reconnect reloads the viewer and
replays a bounded cached keyframe group so a static app can appear immediately.

| Viewer | Useful for | Tradeoff |
| --- | --- | --- |
| Browser scrcpy, included | Direct Android video in the preview pane with coordinated input | WebCodecs required; basic ADB input rather than full native gestures |
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

The project reuses upstream capture and decoding instead of maintaining a
scrcpy fork. [NetrisTV/ws-scrcpy](https://github.com/NetrisTV/ws-scrcpy) offers
another browser UI, but its README documents a modified scrcpy 1.19 server
(reviewed 2026-09-05). Tango lets this bridge use an official newer server.
