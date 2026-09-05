# Interactive Docker emulator

Use [Android Agent Lab](https://github.com/Hashim-K/android-agent-lab), a small
Compose setup around budtmo/docker-android with its upstream noVNC viewer.
The derived image runs Android 16 / API 36.1 using a Pixel 9 profile. It adds
a stable Android 16 system image to the upstream browser/emulator infrastructure.
Locate the checkout supplied by the user. If this skill is loaded from that
checkout, `scripts/lab.py` is three directories above this reference file.
Resolve symlinks first. A skill installed on its own still needs the lab
checkout to launch Docker; its generic ADB coordinator remains self-contained.

On a Linux x86_64 KVM host, from the lab checkout:

```bash
python3 scripts/lab.py doctor
python3 scripts/lab.py up
python3 scripts/lab.py url
python3 scripts/lab.py status
python3 scripts/lab.py claim --owner 'codex:unique-thread-id' --note 'Test current build'
```

`up` creates a local password if `.env` is absent and waits for Android boot.
If Android fails to boot, inspect the device log given by the error. Do not
declare success just because Docker reports the container running.

The lab targets `127.0.0.1:15555` by default; its wrapper reads custom ports from
`.env`. Use `lab.py adb --token TOKEN -- ...` and `lab.py screenshot --token
TOKEN --out /tmp/new-screen.png`. These use the same registry as `adb_coord.py`.
Do not alternate with the container-internal serial `emulator-5554`.

Open the printed browser URL with the client's available preview tool. Use
`url --with-password` only for a private preview; that URL contains a credential.
When the preview runs elsewhere, forward the web port over SSH. The noVNC canvas
supports mouse/keyboard control; ADB provides agent actions and screenshots.
Browser inspection cannot read native widget semantics from the canvas.

This preview is the running emulator. Android Studio's design-time previews,
inspector, debugger, and profiling integrations are not embedded here.

Use `release` for a human turn, or hand off to `--owner 'human:NAME'` and give the
user the resulting token. A live human claim blocks cooperating agents; noVNC
itself stays interactive regardless of who owns the claim. Never promise
enforced human/agent exclusion.

`python3 scripts/lab.py down` stops this lab and keeps Android data. It rejects
an active claim unless supplied its token. Do not use global Docker prune/stop
commands or delete an existing emulator volume as routine recovery.
