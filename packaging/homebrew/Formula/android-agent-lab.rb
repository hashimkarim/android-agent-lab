class AndroidAgentLab < Formula
  desc "Shared Android devices, scrcpy video, and visible agent cursors"
  homepage "https://github.com/hashimkarim/android-agent-lab"
  version "0.2.0"
  license "MIT"
  depends_on :linux
  depends_on "python@3.14"

  if Hardware::CPU.arm?
    url "https://github.com/hashimkarim/android-agent-lab/releases/download/v#{version}/Android-Agent-Lab-#{version}-arm64.tar.gz"
    sha256 "dc57df5fb2c6bbf76baf0352471031d5c7f1f463e1165c2ecb488d48f259e96e"
  else
    url "https://github.com/hashimkarim/android-agent-lab/releases/download/v#{version}/Android-Agent-Lab-#{version}-x64.tar.gz"
    sha256 "fd326e5337cf2f433cf9d6e80b9db03d850a669a1c82174309f32c73ffacb18d"
  end

  def install
    libexec.install Dir["*"]
    (bin/"android-agent-lab").write <<~SH
      #!/bin/sh
      unset ELECTRON_RUN_AS_NODE
      export ADB_LAB_PYTHON="${ADB_LAB_PYTHON:-#{formula_opt_bin("python@3.14")}/python3.14}"
      exec "#{libexec}/android-agent-lab" "$@"
    SH
    (share/"applications/android-agent-lab.desktop").write <<~DESKTOP
      [Desktop Entry]
      Type=Application
      Name=Android Agent Lab
      Comment=Shared Android devices, scrcpy video, and visible agent cursors
      Exec=#{opt_bin}/android-agent-lab %U
      Icon=android-agent-lab
      Terminal=false
      StartupWMClass=android-agent-lab
      Categories=Development;Utility;
      Keywords=Android;ADB;Emulator;scrcpy;Codex;Claude;
    DESKTOP
    # Extract the small icon from the release's ASAR without executing the app.
    asar = libexec/"resources/app.asar"
    File.open(asar, "rb") do |file|
      file.seek(12)
      header_length = file.read(4).unpack1("V")
      header = JSON.parse(file.read(header_length))
      entry = header.fetch("files").fetch("app").fetch("files").fetch("icon.png")
      file.seek(4)
      data_offset = 8 + file.read(4).unpack1("V")
      file.seek(data_offset + Integer(entry.fetch("offset")))
      icon = share/"icons/hicolor/256x256/apps/android-agent-lab.png"
      icon.dirname.mkpath
      icon.binwrite(file.read(entry.fetch("size")))
    end
  end

  def caveats
    <<~EOS
      Requires a Linux desktop with GTK 3, NSS, GBM and ALSA libraries, plus adb.
      Install adb using your distro's android-tools/adb package or Android SDK.
      For nearby discovery with distro adb, install and enable Avahi.
      Docker with Compose and /dev/kvm is optional for the x86_64 Android emulator.

      Launch with: android-agent-lab
      Add #{HOMEBREW_PREFIX}/share to XDG_DATA_DIRS for the application menu.
      Ubuntu users with restricted user namespaces should use the PPA/DEB package,
      which installs an AppArmor profile for Chromium's sandbox.
    EOS
  end

  test do
    assert_path_exists libexec/"resources/runtime/skills/adb-coordination/SKILL.md"
    assert_path_exists share/"icons/hicolor/256x256/apps/android-agent-lab.png"
    python = formula_opt_bin("python@3.14")/"python3.14"
    output = shell_output("#{python} #{libexec}/resources/runtime/scripts/lab.py --help")
    assert_match "shared ADB coordinator", output
    # Headless check of the exact bundled runtime; GUI smoke testing uses Xvfb.
    assert_match "v24.", shell_output("ELECTRON_RUN_AS_NODE=1 #{libexec}/android-agent-lab --version")
  end
end
