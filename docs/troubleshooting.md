# Boot and preview troubleshooting

Check the actual guest, container status, and emulator log:

```bash
python3 scripts/lab.py doctor
python3 scripts/lab.py status
python3 scripts/lab.py wait --timeout 60
docker compose logs --tail 100 emulator
docker compose exec -T emulator tail -100 /home/androidusr/logs/device.stdout.log
```

Upstream's supervisor can remain alive after the emulator process crashes.
The launcher and Compose health check test Android's `sys.boot_completed`
property instead. This is a boot check; it does not certify that Android's UI
services or the tested app remain healthy. Optional upstream services such as Appium can log supervisor
errors when disabled; inspect the device log for emulator failures.

## Graphics

This configuration uses the emulator's bundled **Lavapipe** software renderer
(`-gpu lavapipe`), so host GPU passthrough is unnecessary. During initial
validation, the upstream default SwiftShader renderer and an explicit
`-gpu swiftshader -feature -Vulkan` both crashed with SIGSEGV.

The default also enables `GLDirectMem,HasSharedSlotsHostMemoryAllocator`.
Without them, Android 16's SurfaceFlinger repeatedly aborted in
`mapper.ranchu.so` with `Assertion failed: !rcEnc->featureInfo()->hasReadColorBufferDma`.
The [Android mapper source](https://android.googlesource.com/device/generic/goldfish/+/refs/heads/main/hals/gralloc/mapper.cpp)
calls `LOG_ALWAYS_FATAL_IF` when that capability is absent; the message does
not mean that it must be disabled. The
[host implementation](https://android.googlesource.com/platform/hardware/google/gfxstream/+/refs/heads/main/host/RenderControl.cpp)
advertises it when both features are enabled. Explicitly enabling both fixed
the repeated graphics-service crash in the tested Android 16 configuration.

`-feature -ModemSimulator` uses the legacy modem implementation. It avoids the
new modem simulator's `::1` address-resolution error observed in the Docker
network; it does not disable host IPv6 or alter host sysctls.

Change `EMULATOR_ARGS` in `.env` to experiment with supported options after
releasing claims and stopping the lab. Keep `-no-snapshot` while diagnosing
graphics changes, so an older graphics state is not restored. Query the pinned
binary's supported modes with:

```bash
docker compose exec -T emulator emulator -help-gpu
```

[Android's emulator troubleshooting guide](https://developer.android.com/studio/run/emulator-troubleshooting)
contains additional graphics and boot guidance. Docker still depends on the
host's kernel, CPU virtualization, and available memory; it does not remove all
emulator compatibility problems.

## Data partition fills during first boot

Compose sets `EMULATOR_DATA_PARTITION=8g`. Upstream's default is only 550 MB;
Android 16 filled it during setup and system services failed with full-database
errors. Check the guest filesystem with:

```bash
docker compose exec -T emulator adb -s emulator-5554 shell df -h /data
```

Changing the environment variable does not migrate an existing AVD. Back up
any app data and use a new named volume when changing its size. Do not remove
an existing volume containing work you need to preserve.

## Stale AVD lock after a crash

An unclean emulator exit may leave `hardware-qemu.ini.lock` in the persisted AVD.
In a new container its old PID can refer to an unrelated process, causing the
emulator to report that another instance already uses the same AVD.

First inspect this lab's processes and claim. Stop the lab and confirm no
container using its volume is running. Only then move the stale AVD lock aside
in a one-off container. For the default Compose project:

```bash
python3 scripts/lab.py down
docker compose run --rm --no-deps --entrypoint /bin/sh emulator -c 'if test -f /home/androidusr/emulator/hardware-qemu.ini.lock; then mv /home/androidusr/emulator/hardware-qemu.ini.lock /home/androidusr/emulator/hardware-qemu.ini.lock.stale; fi'
python3 scripts/lab.py up
```

Supply the live owner's token to `down` if a claim is active. This moves only
the upstream AVD's stale lock, preserves app data, and does not change the
coordinator's `.lock` files. Never remove coordinator lock files: replacing a
lock inode can allow two concurrent owners.

## Android 17 compatibility result

API 37.0 revision 6 booted and reported Android 17, but its graphics service
hit the same missing-capability failure described above. The framework
restarted while `sys.boot_completed` continued to report 1. Those tests preceded
the corrected graphics configuration. Android 17 has not been validated with
the final configuration and is not currently a supported image here. Android
16 / API 36.1 is the tested default; no Android graphics binaries are patched.

## Browser

`python3 scripts/lab.py url --with-password` prints a private autoconnect URL.
If the VNC password changed, reconnect using the new URL. The server publishes
only on loopback; remote previews need forwarding on the machine that runs the
browser backend, as described in the skill's client reference.

The display is a portrait desktop containing the upstream emulator window.
`-screen multi-touch` creates the guest touch device required for browser
clicks and drags. Without it, this system image exposed only keyboard devices;
ADB-injected taps worked but desktop mouse input did not reach the app.
Use noVNC's scaling setting if it looks too large. A first click may focus the
window; inspect the resulting screen before repeating an action. Browser
screenshots can briefly lag a delivered input; use a later screenshot or a
coordinated Android UI query to verify the result.

## Validation scope

The isolated test suite checks concurrent claims, token rotation, expiration,
timeouts, exact ADB targeting, launcher configuration, credential handling,
ownership checks before stopping, and boot readiness. It uses no real devices.

Runtime validation on 2026-09-05 used Linux x86_64, KVM, Fedora 44, Docker 29,
Android Emulator 37.1.11, and the Android 16 / API 36.1 revision 4 Google APIs
image. The guest reported release `16` and SDK `36`. The following passed:

- Boot with the 8 GB data partition and corrected graphics flags.
- Installation and launch of a small local native Android test APK.
- Claimed ADB taps, text input, PNG screenshots, and UI hierarchy inspection.
- Browser clicks incrementing the app's counter and keyboard input appearing
  in its text field, verified through the Android UI hierarchy.
- Container removal and recreation preserving the installed APK and its saved
  counter; the upstream log confirmed reuse of the AVD without `-wipe-data`.
- Stable SurfaceFlinger and system_server process IDs across app interaction
  and screenshot capture, over several minutes before restart.

The temporary test APK is not bundled. Google Play Services logged a background
exception during first-boot setup; Google account and Play Services integration
were not validated. These are local smoke tests, not cross-platform or load-test
certification. Android 17's earlier result is described above.
