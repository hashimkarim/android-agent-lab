# Live physical devices

Use the same coordinator and claim registry for phones, tablets, and emulators.
Do not use `lab.py` for a USB phone: that shortcut always targets the Docker
emulator. Resolve the scripts below relative to this skill's directory.

## Connect and identify

For USB, enable Developer options and USB debugging on the intended phone,
connect a data-capable cable, and let the user approve its debugging prompt.
Run `python3 scripts/adb_coord.py devices` and select its exact serial.
`unauthorized` requires phone-side approval; `offline` is not a usable device.
Inspect the cable and connection before considering any shared-server changes.

For Android 11+ wireless debugging, use the phone's **Pair using pairing code**
screen. On the device host, run `adb pair ADDRESS:PAIRING_PORT` and enter the
displayed code when prompted. If necessary, use `adb connect ADDRESS:CONNECT_PORT`
from the main Wireless debugging screen; the two ports can differ. Respect a
custom `ADB_SERVER_SOCKET` by passing `adb -L SOCKET` for these setup commands.
Rediscover the actual connected serial afterwards. See
[Google's ADB instructions](https://developer.android.com/tools/adb#connect-to-a-device-over-wi-fi).

USB and Wi-Fi can expose the same phone under different serials. These are
not independent devices and do not share a claim automatically. Choose one
transport and canonical serial for the task, record it in handoffs, and inspect
other claims before switching. Do not disconnect another thread's transport.

## Claim, inspect, and hand off

```bash
python3 scripts/adb_coord.py status
python3 scripts/adb_coord.py claim --serial SERIAL --owner 'codex:THREAD_ID' --project /path/to/app --note 'Physical phone via USB; verify settings'
python3 scripts/adb_coord.py screenshot --serial SERIAL --token TOKEN --out /tmp/phone-new.png
python3 scripts/adb_coord.py run --serial SERIAL --token TOKEN -- install -r /path/to/app-debug.apk
python3 scripts/adb_coord.py handoff --serial SERIAL --token TOKEN --owner 'claude:NEXT_THREAD' --note 'Same USB phone; settings open'
```

Use the returned token only for that thread. Preserve personal app data and
the user's current screen unless the requested test calls for an interaction.
App installation does not authorize clearing data or uninstalling to work around
signing errors. Stop only previews started for this task; never shut down or
reboot a physical phone as preview cleanup.

## Live video and portable preview

Use [video.md](video.md) for scrcpy video with coordinated browser controls.
It works with the same live-device serial and needs the lab checkout and Node.
The following screenshot viewer is self-contained within this skill:

```bash
python3 scripts/adb_preview.py --serial SERIAL --token TOKEN --duration 1800
```

Open the complete printed URL in the preview pane. The included viewer polls
screenshots about once per second; it is a lightweight inspection fallback,
not smooth video. Add `--control` for taps, swipes, Back, Home, and Recents.
Each input and frame checks ownership. Handoff/release revokes the old viewer;
passive refreshes do not extend the claim. Pause refreshes during a batch of
agent commands if they contend. Keep the access-key fragment in the URL and
retain the exact server PID for cleanup. It binds to loopback and expires after
the selected duration. Remote browser hosts require an SSH tunnel.

For smooth desktop mirroring, scrcpy can target the same serial. It bypasses
the wrapper's per-command lock, so respect the active claim and take turns.
Use `--no-control` for observation and close its exact process before handoff.
