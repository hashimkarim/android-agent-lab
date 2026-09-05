# Reuse decision

Source review: 2026-09-05. This project reuses upstream runtime components. A
small derived image installs Google's Android 16 system image, adds its
version mapping to the public upstream launcher, and fixes its Pixel profile
name comparison so restarts preserve the AVD. The public version table ends at Android 14.
This is a local adaptation, not an official budtmo Android 16 image or its Pro
edition. The stable SDK package is `android-36.1`; the device reports SDK 36 with its minor API update.

**budtmo/docker-android** supplies a desktop emulator, browser noVNC, ADB access,
and documented Android 9–14 free images. Its beta MCP server is worth watching;
the inspected implementation supports operations such as opening known apps,
URLs, and hardware keys, but does not provide this repository's device leases
or thread handoffs. Using that server later would not require replacing the
runtime selected here.

- [README](https://github.com/budtmo/docker-android)
- [MCP implementation](https://github.com/budtmo/docker-android/blob/master/mcp/src/server.py)
- [Analytics opt-out](https://github.com/budtmo/docker-android/blob/master/documentations/USER_BEHAVIOR_ANALYTICS.md)
- [License](https://github.com/budtmo/docker-android/blob/master/LICENSE.md)

**HQarroum/docker-android** is a useful minimal headless runtime. Its documented
interactive path uses scrcpy; browser embedding requires a separate browser
bridge. It is a good alternative for CI and workflows already using desktop
scrcpy, but adds a component for this particular browser-preview requirement.

- [Source and documentation](https://github.com/HQarroum/docker-android)

**Shmayro/dockerify-android** has a scrcpy-web companion and is another valid
starting point. At review time the checked-in Dockerfile defaults to API 30
(Android 11), and the checked-in image publishing workflow builds linux/amd64.
The README's wider multiarchitecture claims need separate validation before
using it as an Apple Silicon answer.

- [Dockerfile and project](https://github.com/Shmayro/dockerify-android)
- [Browser companion](https://github.com/Shmayro/ws-scrcpy-docker)

The [Bright Coding guide](https://prompts.brightcoding.dev/blog/run-android-emulators-in-docker-the-ultimate-guide-for-scalable-mobile-app-testing)
and [Medium tutorial](https://medium.com/@Amr.sa/running-android-emulator-in-a-docker-container-19ecb68e1909)
are introductory setup guides, not additional runtimes. Image tags, environment
variables, and supported platforms should come from the selected project's
current source and documentation.

The incremental benefit of custom code is coordination across cooperating
clients. Rebuilding screen streaming, touch transport, or Android installation
would duplicate existing work and create a much larger maintenance obligation.

Android 17 / API 37.0 revision 6 initially hit the same missing graphics
capability later diagnosed and corrected on Android 16. It has not been
retested with the final configuration. Android 16 / API 36.1 is the tested
modern default. See the [runtime verification record](troubleshooting.md);
the project does not maintain an emulator or Android graphics fork.

## Android CLI, Studio, and on-device agents

[Google's Android CLI](https://developer.android.com/tools/agents/android-cli)
and [official skills](https://github.com/android/skills) are the preferred source
for Android-specific development workflows. The inspected CLI includes device
installation/running, screen capture, visual targeting, layout inspection, and
Studio integration, including Compose preview rendering. It does not supply the
browser noVNC session or this repository's cross-thread ownership registry.
Use it for those existing capabilities instead of adding another SDK/framework
implementation here. Other tools do not automatically participate in the lock;
respect active claims and avoid parallel device commands from the same owner.

[Android Studio Agent Mode](https://developer.android.com/studio/gemini/agent-mode)
can deploy, inspect, capture, and interact with apps. It is a useful alternative
if work should happen inside Studio. That integration does not by itself share
ownership with separate Codex/Claude/T3 threads. The user's linked Fall Android
Show announcement describes Studio and app-AI capabilities, not a general
container/browser bridge.

[Deadolus/android-studio-docker](https://github.com/Deadolus/android-studio-docker)
provides the full Android Studio desktop and emulator using display forwarding.
It is not documented as a browser viewer out of the box. The linked Reddit
browser-Studio post instead points to
[devapro/docker-android-studio](https://github.com/devapro/docker-android-studio),
which includes noVNC and lists the emulator not working in Studio's Devices
tool window as a known issue. A full IDE desktop suits users who need Studio
inspectors; it adds resource use and a larger UI to a narrow preview pane.

[ADK for Kotlin/Android](https://google.github.io/adk-docs/) builds agents within
apps and JVM services. The linked Reddit "Agentic OS" post proposes system-level
app orchestration. These concern application/OS architecture and do not replace
the development emulator or shared device-access protocol.
