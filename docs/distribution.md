# Package manager installation

Android Agent Lab is distributed through the project's community package channels
and [GitHub Releases](https://github.com/hashimkarim/android-agent-lab/releases).
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

The `-bin` recipe packages the published release binaries. For a helper-free
installation, follow the [ArchWiki prerequisites and review guidance](https://wiki.archlinux.org/title/Arch_User_Repository):

```bash
sudo pacman -Syu --needed base-devel git
git clone https://aur.archlinux.org/android-agent-lab-bin.git
cd android-agent-lab-bin
# Review PKGBUILD and accompanying build/install files before building.
makepkg -si
```

Run `makepkg` as your regular user. The recipe supports x86_64 Arch Linux and
compatible aarch64 Arch Linux ARM installations.

## Fedora 43 and 44

Enable the [Android Agent Lab COPR](https://copr.fedorainfracloud.org/coprs/hashimkarim/android-agent-lab/):

```bash
sudo dnf install dnf5-plugins
sudo dnf copr enable hashimkarim/android-agent-lab
sudo dnf install android-agent-lab
```

Both x86_64 and aarch64 builds are provided.
[`dnf5-plugins`](https://packages.fedoraproject.org/pkgs/dnf5/dnf5-plugins/) supplies
the `copr` command on these Fedora releases.

## Ubuntu 24.04 LTS (amd64)

Install from the [Android Agent Lab PPA](https://launchpad.net/~hashimkarim/+archive/ubuntu/android-agent-lab):

```bash
sudo apt update
sudo apt install software-properties-common
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

Follow [Homebrew's installation prerequisites](https://docs.brew.sh/Installation)
and its shell setup first. Then install the fully qualified formula from
[hashimkarim's tap](https://github.com/hashimkarim/homebrew-tap/blob/main/Formula/android-agent-lab.rb):

```bash
brew install hashimkarim/tap/android-agent-lab
android-agent-lab
```

Current Homebrew [trusts the named formula](https://docs.brew.sh/Tap-Trust) when
you use its fully qualified install command. If your version asks for trust,
review and approve `hashimkarim/tap/android-agent-lab` specifically. You can also use
`brew trust --formula hashimkarim/tap/android-agent-lab`; whole-tap trust is unnecessary.

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
DEB, which installs the app's AppArmor profile.

## AppImage, RPM, DEB and portable downloads

All ten architecture-specific installers remain available from
[GitHub Releases](https://github.com/hashimkarim/android-agent-lab/releases), with
`SHA256SUMS` and the user-local AppImage installer. See the
[desktop guide](desktop.md) for dependencies and installation details.

## First run

```bash
android-agent-lab --version
android-agent-lab
```

The first command prints the installed version; the second opens the device
workspace. Plug in a USB device with debugging enabled and accept its authorization
prompt, or use **Add phone**. **Open device** starts the shared viewer. From a
Gradle project's directory, `android-agent-lab .` adds or reopens it in the library.
See the [workspace guide](desktop.md#use-the-shared-screen) for pairing and agent access.

## Upgrade and uninstall

Quit the launcher before updating, then reopen it to use the new version.
Use **Stop** on each emulator you want to turn off; quitting the launcher stops
its video sessions but leaves emulators and their Android data in place.

| Channel | Upgrade | Remove the app |
| --- | --- | --- |
| AUR | `yay -Syu android-agent-lab-bin`, or update and review the cloned recipe with `git pull --ff-only`, then `makepkg -si` | `sudo pacman -R android-agent-lab-bin` |
| Homebrew | `brew update`, then `brew upgrade hashimkarim/tap/android-agent-lab` | `brew uninstall hashimkarim/tap/android-agent-lab` |
| COPR | `sudo dnf upgrade android-agent-lab` | `sudo dnf remove android-agent-lab` |
| PPA | `sudo apt update`, then `sudo apt install --only-upgrade android-agent-lab` | `sudo apt remove android-agent-lab` |
| Direct DEB / RPM / Arch package | Verify the new download and repeat its installation command | `sudo apt remove android-agent-lab`, `sudo dnf remove android-agent-lab`, or `sudo pacman -R android-agent-lab` respectively |
| AppImage / tar archive | [Replace the verified image or extracted runtime](desktop.md#upgrade-and-remove-portable-installs) | [Remove its launcher and runtime](desktop.md#upgrade-and-remove-portable-installs) |

App removal preserves your projects, saved APKs, device names, claims and emulator
data. See [local data locations](desktop.md#local-files-and-remote-hosts). Do not
delete your workspace or Docker volumes as part of a routine uninstall.

Removing a package does not remove its repository. If you no longer use any
packages from a channel, you can also remove its configuration:

```bash
# Homebrew: only after removing every formula you use from this shared tap.
brew untap hashimkarim/tap
# Fedora: remove this COPR repository configuration.
sudo dnf copr remove hashimkarim/android-agent-lab
# Ubuntu: remove this PPA and refresh package lists.
sudo add-apt-repository --remove ppa:hashimkarim/android-agent-lab
sudo apt update
```

Run only the commands for the channel you installed. AUR recipes do not add a
pacman repository; the cloned recipe directory can be removed separately.

## Maintaining the channels

The checked-in recipes live under [`packaging`](../packaging). They repackage
the same verified release binaries, preserve their third-party notices, install
menu entries, and provide an `android-agent-lab` terminal launcher that clears
`ELECTRON_RUN_AS_NODE`. AUR installs into `/usr/lib/android-agent-lab`, RPM/DEB
into `/opt/android-agent-lab`, and Homebrew into its versioned Cellar.

### Automatic stable releases

[`desktop.yml`](../.github/workflows/desktop.yml) tests and builds both architectures,
checks that the tag matches `desktop/package.json`, then creates the GitHub release
and its checksums. After a stable `vMAJOR.MINOR.PATCH` release, it calls
[`publish-packages.yml`](../.github/workflows/publish-packages.yml) directly. This
also works when the release was created with `GITHUB_TOKEN`, whose events do not
start another release-triggered workflow. Prereleases stay on GitHub.

Versions and hashes are generated from the selected release; checked-in recipe
versions are templates and do not need manual bumps for each upstream release.
Both `.tar.gz` bundles must match the published `SHA256SUMS`. The preparer checks
ELF architectures, required runtime resources, the embedded app version, matching
app code between architectures, and archive paths before staging distro packages.
Never replace assets beneath an existing tag.

Each platform runs independently and serializes updates to its package repository:

| Channel | Required validation before upload | Destination |
| --- | --- | --- |
| AUR | Unprivileged `makepkg`, generated `.SRCINFO`, package installation and app smoke test | `aur.archlinux.org/android-agent-lab-bin.git`; only `PKGBUILD` and `.SRCINFO` |
| Homebrew | Install the generated formula in an isolated tap, `brew test`, app smoke test | `hashimkarim/homebrew-tap`, only `Formula/android-agent-lab.rb` |
| COPR | Build the complete SRPM and RPM in Fedora 44, install and smoke-test the RPM | `hashimkarim/android-agent-lab`; existing Fedora 43/44 x86_64 and aarch64 chroots |
| PPA | Build unsigned source on Ubuntu 24.04, extract its `.dsc`, build/install the binary, app smoke test | Signed source `.changes` to `ppa:hashimkarim/android-agent-lab`, Noble amd64 |

Smoke tests use Xvfb as a normal user with a fresh profile. They check Python,
bundled Node, renderer isolation and H.264 support without interacting with Android
devices. These distro checks run on x86_64; the desktop release workflow separately
builds and tests ARM64 natively. COPR subsequently builds both enabled architectures.
The PPA's enabled architectures and series are preserved.

### Dry runs and retries

In Actions, run **Publish package repositories** with the latest existing stable
tag. `dry_run` defaults to `true`; select `all` or one platform. Dry runs execute
the same package builds and installation checks, without passing platform secrets
to the step or uploading packages. Inspect the logs and `publishing-*` artifacts.

After the workflow is on the default branch, a CLI equivalent is:

```bash
gh workflow run publish-packages.yml --repo hashimkarim/android-agent-lab \
  -f tag=v0.2.0 -f platform=all -F dry_run=true
```

Use the current latest tag. To publish or retry a specific platform, choose that
platform and explicitly set `dry_run=false`. The workflow checks the latest stable
release again immediately before writing. It rejects downgrades and checks existing
submissions before uploading. API failures fail the job; they never count as an
absent package. Pending COPR/PPA submissions are polled with cache revalidation and
a 45-minute limit. A timeout does not cancel the remote build: check it before retrying.
Already published versions are reused, and the other channels need not be rerun.

Production COPR runs also synchronize the homepage and description from
`packaging/copr/project.json`, including retries of an already published version.
Only changed metadata fields are written; project instructions, build settings,
permissions, and existing uploads are preserved. This requires project admin
access and the Python SDK installed with `copr-cli` in the same Python environment.
Dry runs leave project metadata untouched. Updated AUR, Homebrew and PPA package
links take effect when the next version is published.

For a failed COPR build, retry the platform job. For a failed Launchpad build, use
Launchpad's **Retry build** and rerun the PPA job to observe publication. Launchpad
does not allow reuploading the same Debian version. For a packaging-only change,
increment the distro revision and preserve the original upstream tarball; do not
regenerate a different `.orig.tar.gz` under a used upstream version. The generator
retains the existing `0.2.0-1ppa2` revision; subsequent upstream versions start at
`-1ppa1`. Updating packaging revisions requires a deliberate recipe/helper change.
Installed Debian timestamps are normalized with `SOURCE_DATE_EPOCH` because
Launchpad rejects epoch-zero payload timestamps.

### Repository configuration

Configure these Actions secrets and variables on the **source** repository:

| Platform | Secrets | Variables |
| --- | --- | --- |
| AUR | `AUR_SSH_PRIVATE_KEY` | `AUR_SSH_KNOWN_HOSTS` (verified host keys) |
| Homebrew | `HOMEBREW_SSH_PRIVATE_KEY` | `HOMEBREW_TAP_REPOSITORY=hashimkarim/homebrew-tap` |
| COPR | `COPR_CONFIG` (existing copr-cli configuration) | Destination is fixed in the helper |
| PPA | `PPA_GPG_PRIVATE_KEY`; optional `PPA_GPG_PASSPHRASE` | `PPA_GPG_FINGERPRINT` |

Missing configuration fails the affected platform explicitly. The Homebrew deploy
key needs write access only to the tap. Register the AUR key on the maintainer's
account and the OpenPGP key on Launchpad. Use a signing subkey for CI; keep the
primary private key local. Reuse the existing COPR token: creating another personal
token invalidates the previous one. Platform secrets never enter the package-test
containers or public artifacts; temporary credential files are removed on exit.

Maintainers using the private `linux-deploy` toolkit can preview and install this
configuration with its `scripts/secrets.py install --repo hashimkarim/android-agent-lab
--platform aur homebrew copr ppa`, then `--apply`. Do not copy its `.env` into this
repository. Existing credential sets are preserved unless replacement is explicitly
requested. Fork maintainers must change the recipe URLs, helper destinations and
workflow repository names to accounts they control, and register their own keys.

### Local validation

Python 3.10+, Docker and GitHub CLI are sufficient for a local dry run. Use a native
Linux filesystem with several GB free for staging; Electron's profile and sandbox
tests need normal Unix permissions. Download and prepare once, then validate each
platform (the output directory must not exist yet):

```bash
tag=v0.2.0
staging="$HOME/.cache/android-agent-lab-publishing/$tag"
python3 tools/publish/scripts/release-info.py "$tag"
gh release download "$tag" --repo hashimkarim/android-agent-lab \
  --pattern '*.tar.gz' --pattern SHA256SUMS --dir "$staging/assets"
python3 scripts/prepare_distribution.py --tag "$tag" \
  --assets "$staging/assets" --output "$staging/prepared"
for platform in aur homebrew copr ppa; do
  DRY_RUN=true RELEASE_TAG="$tag" bash tools/publish/scripts/publish-platform.sh \
    "$platform" "$staging/prepared"
done
python3 -m unittest discover -s tools/publish/tests -v
```

[`publishing-tests.yml`](../.github/workflows/publishing-tests.yml) runs the regression
tests, ShellCheck and actionlint on changes to publishing helpers, recipes or workflows.
