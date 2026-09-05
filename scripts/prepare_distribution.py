#!/usr/bin/env python3
"""Stage distro recipes from verified GitHub release assets; never uploads."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True, help="Release downloads, including SHA256SUMS")
    parser.add_argument("--output", type=Path, required=True, help="New staging directory")
    args = parser.parse_args()
    assets, output = args.assets.resolve(), args.output.resolve()
    if output.exists():
        parser.error("output already exists; choose a new staging directory")
    version = json.loads((ROOT / "desktop/package.json").read_text())["version"]
    checksums = {}
    for line in (assets / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        checksums[name] = digest
    names = [f"Android-Agent-Lab-{version}-{arch}.{extension}" for arch, extension in
             [("x64", "tar.gz"), ("arm64", "tar.gz"), ("x64", "pkg.tar.zst"), ("aarch64", "pkg.tar.zst")]]
    for name in names:
        with (assets / name).open("rb") as source:
            digest = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != checksums.get(name):
            parser.error(f"checksum mismatch: {name}")

    aur_recipe = (ROOT / "packaging/aur/android-agent-lab-bin/PKGBUILD").read_text()
    brew_recipe = (ROOT / "packaging/homebrew/Formula/android-agent-lab.rb").read_text()
    for name in names:
        recipe = aur_recipe if name.endswith(".zst") else brew_recipe
        if checksums[name] not in recipe:
            parser.error(f"recipe checksum does not match release: {name}")
    versions = {
        "AUR": re.search(r"^pkgver=(.+)$", aur_recipe, re.M).group(1),
        "Homebrew": re.search(r'  version "([^"]+)"', brew_recipe).group(1),
        "RPM": re.search(r"^Version:\s+(\S+)", (ROOT / "packaging/rpm/android-agent-lab.spec").read_text(), re.M).group(1),
        "Debian": re.search(r"\(([^-]+)-", (ROOT / "packaging/debian/changelog").read_text()).group(1),
    }
    if any(value != version for value in versions.values()):
        parser.error(f"recipes must match release {version}: {versions}")

    shutil.copytree(ROOT / "packaging/aur/android-agent-lab-bin", output / "aur")
    copy(ROOT / "packaging/homebrew/Formula/android-agent-lab.rb", output / "homebrew/Formula/android-agent-lab.rb")
    rpm = output / "rpm"
    copy(ROOT / "packaging/rpm/android-agent-lab.spec", rpm / "SPECS/android-agent-lab.spec")
    for name in ("BUILD", "BUILDROOT", "RPMS", "SRPMS"):
        (rpm / name).mkdir(parents=True, exist_ok=True)
    source = output / "ppa" / f"android-agent-lab-{version}"
    common = source / "packaging/common"
    for name in ("android-agent-lab", "android-agent-lab.desktop"):
        copy(ROOT / "packaging/common" / name, common / name)
        copy(ROOT / "packaging/common" / name, rpm / "SOURCES" / name)
    copy(ROOT / "desktop/build/icons/256x256.png", common / "android-agent-lab.png")
    copy(ROOT / "desktop/build/icons/256x256.png", rpm / "SOURCES/android-agent-lab.png")
    copy(ROOT / "LICENSE", source / "LICENSE")
    for name in names:
        if name.endswith(".zst"):
            copy(assets / name, output / "aur" / name)
        else:
            copy(assets / name, source / "prebuilt" / name)
            copy(assets / name, rpm / "SOURCES" / name)
    sums = "".join(f"{checksums[name]}  {name}\n" for name in names if name.endswith(".tar.gz"))
    (source / "prebuilt/SHA256SUMS").write_text(sums)
    (rpm / "SOURCES/SHA256SUMS").write_text(sums)
    # Keep Debian metadata out of the pristine upstream tarball.
    with tarfile.open(output / "ppa" / f"android-agent-lab_{version}.orig.tar.gz", "w:gz") as archive:
        archive.add(source, arcname=source.name)
    shutil.copytree(ROOT / "packaging/debian", source / "debian")
    copy(ROOT / "packaging/common/android-agent-lab.apparmor", source / "debian/android-agent-lab.apparmor")
    (source / "debian/rules").chmod(0o755)
    print(json.dumps({"version": version, "staged": str(output), "verified_assets": names}, indent=2))


if __name__ == "__main__":
    main()
