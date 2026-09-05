# Package manager installation

Android Agent Lab is distributed through the project's community package channels
and [GitHub Releases](https://github.com/Hashim-K/android-agent-lab/releases).
The desktop app supports x86_64 and ARM64 glibc Linux. The included Docker Android
16 emulator requires x86_64, Docker with Compose, and `/dev/kvm`; physical Android
devices and remote ADB servers work with either desktop architecture.

## Arch Linux and derivatives

Install [android-agent-lab-bin](https://aur.archlinux.org/packages/android-agent-lab-bin)
with your AUR helper:

```bash
yay -S android-agent-lab-bin
# Or: paru -S android-agent-lab-bin
```

Without a helper, clone `https://aur.archlinux.org/android-agent-lab-bin.git`,
review the recipe, and run `makepkg -si` as a normal user. The recipe also supports
compatible Arch Linux ARM installations. Upgrade with your AUR helper.

## Fedora 43 and 44

Enable the [Android Agent Lab COPR](https://copr.fedorainfracloud.org/coprs/hashimkarim/android-agent-lab/):

```bash
sudo dnf copr enable hashimkarim/android-agent-lab
sudo dnf install android-agent-lab
```

Both x86_64 and aarch64 builds are provided. Subsequent updates use `dnf upgrade`.

## Ubuntu 24.04 LTS (amd64)

The [Android Agent Lab PPA](https://launchpad.net/~hashimkarim/+archive/ubuntu/android-agent-lab)
is created; the initial signed package upload is being completed. Once the build
is published, install it with:

```bash
sudo add-apt-repository ppa:hashimkarim/android-agent-lab
sudo apt update
sudo apt install android-agent-lab
```

The PPA currently enables amd64 builds; ARM64 users can use the release's DEB
download. The package includes an AppArmor profile for Chromium's sandbox. Use normal
`apt upgrade` for updates. Other Debian/Ubuntu versions can use the direct DEB
download if they meet its dependency requirements; do not add an Ubuntu PPA to
Debian or to a different Ubuntu series.

## Homebrew on Linux

Install from [Hashim-K's tap](https://github.com/Hashim-K/homebrew-tap):

```bash
brew install hashim-k/tap/android-agent-lab
android-agent-lab
```

This formula supports x86_64 and ARM64 Linux desktops. Homebrew installs Python;
install ADB and the normal GTK 3, NSS, GBM, and ALSA desktop libraries through your
distro's package manager. ADB from Android SDK installations is also detected.
For example, ADB is `adb` on Ubuntu/Debian and `android-tools` on Fedora/Arch.

To expose the menu entry, include Homebrew's share directory in your desktop
session's `XDG_DATA_DIRS`, preserving its existing entries:

```bash
export XDG_DATA_DIRS="$(brew --prefix)/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
```

Ubuntu systems that restrict unprivileged user namespaces should use the PPA or
DEB, which installs the app's AppArmor profile. Upgrade the formula with
`brew update && brew upgrade android-agent-lab`.

## AppImage, RPM, DEB and portable downloads

All ten architecture-specific installers remain available from
[GitHub Releases](https://github.com/Hashim-K/android-agent-lab/releases), with
`SHA256SUMS` and the user-local AppImage installer. See the
[desktop guide](desktop.md) for dependencies and installation details.

## Maintaining the channels

The checked-in recipes live under [`packaging`](../packaging). They repackage
the same verified release binaries, preserve their third-party notices, install
menu entries, and provide an `android-agent-lab` terminal launcher that clears
`ELECTRON_RUN_AS_NODE`. AUR installs into `/usr/lib/android-agent-lab`, RPM/DEB
into `/opt/android-agent-lab`, and Homebrew into its versioned Cellar.

After publishing a new desktop release, update the version in the AUR recipe,
Homebrew formula, RPM spec, and Debian changelog. Update the architecture-specific
checksums in AUR and Homebrew from that release's `SHA256SUMS`. Increment distro
revisions for packaging-only changes. Never replace assets beneath an existing
version: their hashes are pinned by package managers.

Download the release assets into a local directory, then stage the packages:

```bash
python3 scripts/prepare_distribution.py \
  --assets .lab/release-downloads --output .lab/distribution-next
```

The script verifies all four required archives against the release checksums and
pinned recipe hashes. It rejects mismatched versions and existing output
directories. It stages AUR and Homebrew recipes, an RPM build tree with both
architectures, and a Debian source tree with its upstream tarball. It does not
read credentials or publish anything.

Build and check on the corresponding distro, using a clean container or VM:

| Channel | Build / validation | Publish |
| --- | --- | --- |
| AUR | `makepkg -s`, `namcap PKGBUILD`, `namcap android-agent-lab-bin-*.pkg.tar.zst`, `makepkg --printsrcinfo > .SRCINFO` | Push only `PKGBUILD` and `.SRCINFO` to `ssh://aur@aur.archlinux.org/android-agent-lab-bin.git` |
| Homebrew | `brew readall --os=all --arch=all hashim-k/tap`, `brew style`, install and `brew test hashim-k/tap/android-agent-lab` | Copy the formula into `Hashim-K/homebrew-tap` and push its `main` |
| COPR | `rpmbuild -ba --define "_topdir /absolute/staging/rpm" packaging/rpm/android-agent-lab.spec` | `copr-cli build hashimkarim/android-agent-lab /absolute/staging/rpm/SRPMS/*.src.rpm` |
| PPA | In the staged source tree on Ubuntu 24.04: `dpkg-buildpackage -us -uc -S -sa` and `dpkg-buildpackage -us -uc -b` | Sign the source `.changes` with `debsign`, then `dput ppa:hashimkarim/android-agent-lab /absolute/staging/ppa/*_source.changes` |

Ubuntu build tools are `build-essential`, `debhelper`, `dh-apparmor`, `devscripts`,
and `dput`. RPM builds need `rpm-build`, `coreutils`, `tar`, and `gzip`. Arch builds
need `base-devel` and `namcap`. Do not upload built binary archives to AUR Git.

Before publication, install each package and run `android-agent-lab --smoke-test`
as a normal user with a fresh `ADB_LAB_USER_DATA` directory and a GUI session or
Xvfb. This verifies the app version, Python, bundled Node, renderer isolation and
H.264 support without interacting with Android devices. Verify the desktop entry
with `desktop-file-validate`. The initial release passed these installation checks
on Arch, Fedora 44, Ubuntu 24.04, and Homebrew on Linux; upstream release CI also
tested the native ARM64 desktop build.
