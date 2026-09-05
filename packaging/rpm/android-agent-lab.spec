# Repackage the checksum-verified, CI-tested upstream desktop bundles unchanged.
%global debug_package %{nil}
%global __strip /bin/true
%global __brp_mangle_shebangs %{nil}
%global __os_install_post %{nil}
%global _build_id_links none

Name:           android-agent-lab
Version:        0.2.0
Release:        1%{?dist}
Summary:        Shared Android devices, scrcpy video, and visible agent cursors
License:        MIT AND BSD-3-Clause AND Apache-2.0
URL:            https://github.com/Hashim-K/android-agent-lab
Source0:        %{url}/releases/download/v%{version}/Android-Agent-Lab-%{version}-x64.tar.gz
Source1:        %{url}/releases/download/v%{version}/Android-Agent-Lab-%{version}-arm64.tar.gz
Source2:        android-agent-lab
Source3:        android-agent-lab.desktop
Source4:        android-agent-lab.png
Source5:        SHA256SUMS
ExclusiveArch:  x86_64 aarch64
AutoReqProv:    no
BuildRequires:  coreutils
BuildRequires:  tar
BuildRequires:  gzip
Requires:       python3 >= 3.10
Requires:       /usr/bin/adb
Requires:       libgtk-3.so.0()(64bit)
Requires:       libnss3.so()(64bit)
Requires:       libXss.so.1()(64bit)
Requires:       libXtst.so.6()(64bit)
Requires:       xdg-utils
Requires:       libatspi.so.0()(64bit)
Requires:       libuuid.so.1()(64bit)
Requires:       libsecret-1.so.0()(64bit)
Requires:       libgbm.so.1()(64bit)
Requires:       libasound.so.2()(64bit)
Requires:       libc.so.6(GLIBC_2.28)(64bit)

%description
Android Agent Lab provides a Linux desktop app and a shared browser viewer for
Android devices. Humans and coding agents coordinate access through ADB claims,
with scrcpy video, continuous input, named agent cursors, and developer tools.
Docker is optional for the included x86_64 Android 16 emulator.

%prep
cd %{_sourcedir}
sha256sum --check SHA256SUMS
%ifarch x86_64
%setup -q -n Android-Agent-Lab-%{version}-x64
%else
%setup -q -T -b 1 -n Android-Agent-Lab-%{version}-arm64
%endif

%build
# Upstream binaries are preserved, including their bundled third-party licenses.

%install
install -d %{buildroot}/opt/android-agent-lab
cp -a . %{buildroot}/opt/android-agent-lab/
chmod 4755 %{buildroot}/opt/android-agent-lab/chrome-sandbox
install -Dm755 %{SOURCE2} %{buildroot}%{_bindir}/android-agent-lab
install -Dm644 %{SOURCE3} %{buildroot}%{_datadir}/applications/android-agent-lab.desktop
install -Dm644 %{SOURCE4} %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/android-agent-lab.png

%check
test -x %{buildroot}/opt/android-agent-lab/android-agent-lab
test -f %{buildroot}/opt/android-agent-lab/resources/app.asar
test -f %{buildroot}/opt/android-agent-lab/resources/runtime/skills/adb-coordination/SKILL.md

%files
%defattr(-,root,root)
%license resources/runtime/LICENSE LICENSE.electron.txt LICENSES.chromium.html
%{_bindir}/android-agent-lab
%{_datadir}/applications/android-agent-lab.desktop
%{_datadir}/icons/hicolor/256x256/apps/android-agent-lab.png
/opt/android-agent-lab/

%changelog
* Sat Sep 05 2026 Hashim Karim <hashimkarim168@gmail.com> - 0.2.0-1
- Publish the shared Android desktop app and coordination skill.
