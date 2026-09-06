---
name: android-agent-lab-projects
description: Add or reopen local Gradle projects in Android Agent Lab using its global command. Use when the user wants the current project in the app library, or asks to open a project like code . in VS Code.
---

# Android Agent Lab projects

Use the installed `android-agent-lab` command on the user's desktop host. It
opens the app or brings its existing window forward, saves the project, and
selects its card in **Projects & APKs**.

```bash
android-agent-lab .
android-agent-lab "/absolute/path/to/My Android App"
android-agent-lab --project ../my-app
```

Choose the Gradle root containing `gradlew`; for repositories with a nested
Android app, use that directory. Opening registers the path without executing
the wrapper. Reopening the same real directory (including through a symlink)
keeps its saved name, build task, application ID and APK output settings.

Use an absolute, quoted path when the tool's working directory differs from the
project. Pass arguments directly to a process API when available. With a shell,
quote paths as literal arguments; `--` permits a directory name beginning with
a dash. No ADB claim or running emulator is needed to register a project.

Run `android-agent-lab --help` to check command support. The AppImage installer
places the launcher at `~/.local/bin/android-agent-lab`; use that exact path if it
is installed but absent from PATH. A first GUI launch can stay attached to the
terminal: use the tool's background process support and leave the app running.
If an older app is already running, reopen it after updating before sending a
project path. A desktop session is required to open the GUI. Agent terminals sometimes inherit
`ELECTRON_RUN_AS_NODE`; use `env -u ELECTRON_RUN_AS_NODE android-agent-lab ...`
if launching a packaged binary directly from one of those terminals.

Confirm the selected project in the app when GUI tools are available. Otherwise
report that the open request was sent, distinguishing that from an observed UI
result. Do not inspect the app's private workspace JSON to verify registration:
it also contains human device reservation tokens.

The app detects app modules, a debug task, application ID and existing APK metadata.
Builds select a compatible installed JDK and the local Android SDK. The project
card's **Edit settings → Detect settings** shows the resolved paths and settings;
blank overrides follow the repo automatically. Keep explicit overrides for
custom tasks/flavors, relative APK outputs or toolchain paths. Follow the user's
requested scope; adding a project alone does not request a build or device action.
For actual device deployment or testing, use the available `adb-coordination`
skill and the desktop's copied session instructions.
