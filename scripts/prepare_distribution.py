#!/usr/bin/env python3
"""Render distro recipes from a checksum-verified stable release; never publish."""
import argparse
from datetime import datetime, timezone
from email.utils import format_datetime
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('android-agent-lab', 'chrome-sandbox', 'resources/app.asar',
    'resources/runtime/LICENSE', 'resources/runtime/scripts/lab.py',
    'resources/runtime/scripts/video.py', 'resources/runtime/viewer/server.mjs',
    'resources/runtime/viewer/public/client.js',
    'resources/runtime/viewer/node_modules/ws/package.json',
    'resources/runtime/skills/adb-coordination/SKILL.md')


def stable_version(tag):
    if not re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', tag):
        raise ValueError('Package repositories require a stable vMAJOR.MINOR.PATCH tag')
    return tag[1:]


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def replace_one(pattern, replacement, text):
    result, count = re.subn(pattern, lambda _: replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f'Expected one recipe field matching {pattern}; found {count}')
    return result


def checksums(assets):
    result = {}
    for line in (assets / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64}) [ *]([^/\\\s]+)', line)
        if not match or match[2] in result or match[2] in ('.', '..'):
            raise ValueError('Invalid or duplicate SHA256SUMS entry')
        result[match[2]] = match[1]
    return result


def unpack(assets, version, arch, output, sums):
    name = f'Android-Agent-Lab-{version}-{arch}.tar.gz'
    path = assets / name
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != sums.get(name):
        raise ValueError(f'Checksum mismatch: {name}')
    prefix = name[:-7]
    with tarfile.open(path) as tar:
        entries = tar.getmembers()
        names = set()
        for member in entries:
            relative = PurePosixPath(member.name)
            if (not relative.parts or relative.is_absolute() or '..' in relative.parts or relative.parts[0] != prefix
                    or relative.as_posix() != member.name.rstrip('/')
                    or relative.as_posix() in names or not (member.isfile() or member.isdir())):
                raise ValueError(f'Unsafe archive member: {member.name}')
            names.add(relative.as_posix())
        for required in REQUIRED:
            if prefix + '/' + required not in names or not tar.getmember(prefix + '/' + required).isfile():
                raise ValueError(f'Missing runtime resource: {required}')
        for binary in ('android-agent-lab', 'chrome-sandbox'):
            member = tar.getmember(prefix + '/' + binary)
            data = tar.extractfile(member).read(20)
            if (not member.mode & 0o111 or data[:6] != b'\x7fELF\x02\x01'
                    or int.from_bytes(data[18:20], 'little') != {'x64': 62, 'arm64': 183}[arch]):
                raise ValueError(f'Wrong architecture or invalid executable: {arch}/{binary}')
        # All members were checked above, including duplicates, links and devices.
        tar.extractall(output)
    return digest.hexdigest(), output / prefix


def ppa_version(version):
    return version + ('-1ppa2' if version == '0.2.0' else '-1ppa1')


def asar_file(archive, name):
    with archive.open('rb') as stream:
        stream.seek(4); offset = 8 + struct.unpack('<I', stream.read(4))[0]
        stream.seek(12); size = struct.unpack('<I', stream.read(4))[0]
        if size > 8 * 1024 * 1024:
            raise ValueError('Invalid ASAR header size')
        entry = json.loads(stream.read(size))
        for part in name.split('/'):
            entry = entry['files'][part]
        if entry['size'] > 8 * 1024 * 1024:
            raise ValueError('Unexpectedly large ASAR resource')
        stream.seek(offset + int(entry['offset']))
        result = stream.read(entry['size'])
        if len(result) != entry['size']:
            raise ValueError('Truncated ASAR resource')
        return result


def prepare(tag, assets, output, root=ROOT):
    version = stable_version(tag)
    assets, output = assets.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sums = checksums(assets)
    archives = {}; bundles = {}
    for arch in ('x64', 'arm64'):
        digest, bundle = unpack(assets, version, arch, output / 'bundles', sums)
        archives[arch] = dict(name=f'Android-Agent-Lab-{version}-{arch}.tar.gz', sha256=digest)
        bundles[arch] = bundle
    # An architecture mismatch must not smuggle in different app/coordination code.
    for required in REQUIRED:
        if required not in ('android-agent-lab', 'chrome-sandbox') and (bundles['x64'] / required).read_bytes() != (bundles['arm64'] / required).read_bytes():
            raise ValueError(f'Architecture archives disagree on {required}')
    asar = bundles['x64'] / 'resources/app.asar'
    if json.loads(asar_file(asar, 'package.json'))['version'] != version:
        raise ValueError('App version does not match the release tag')
    aur = (root / 'packaging/aur/android-agent-lab-bin/PKGBUILD').read_text()
    aur = replace_one(r'^pkgver=.*$', f'pkgver={version}', aur)
    aur = replace_one(r'^pkgrel=.*$', 'pkgrel=1', aur)
    for arch, release_arch in [('x86_64', 'x64'), ('aarch64', 'arm64')]:
        aur = replace_one(r'^sha256sums_' + arch + r'=.*$', f"sha256sums_{arch}=('{archives[release_arch]['sha256']}')", aur)
    (output / 'aur').mkdir(); (output / 'aur/PKGBUILD').write_text(aur)
    brew = (root / 'packaging/homebrew/Formula/android-agent-lab.rb').read_text()
    brew = replace_one(r'^  version ".*"$', f'  version "{version}"', brew)
    hashes = iter([archives['arm64']['sha256'], archives['x64']['sha256']])
    brew, count = re.subn(r'sha256 "[a-f0-9]{64}"', lambda _: f'sha256 "{next(hashes)}"', brew)
    if count != 2:
        raise ValueError('Expected two Homebrew checksums')
    (output / 'homebrew/Formula').mkdir(parents=True)
    (output / 'homebrew/Formula/android-agent-lab.rb').write_text(brew)
    rpm = output / 'rpm'
    for name in ('BUILD', 'BUILDROOT', 'RPMS', 'SRPMS', 'SOURCES', 'SPECS'):
        (rpm / name).mkdir(parents=True)
    spec = replace_one(r'^Version:.*$', f'Version:        {version}', (root / 'packaging/rpm/android-agent-lab.spec').read_text())
    (rpm / 'SPECS/android-agent-lab.spec').write_text(spec)
    source = output / 'ppa' / f'android-agent-lab-{version}'
    for name in ('android-agent-lab', 'android-agent-lab.desktop'):
        copy(root / 'packaging/common' / name, source / 'packaging/common' / name)
        copy(root / 'packaging/common' / name, rpm / 'SOURCES' / name)
    for destination in (source / 'packaging/common/android-agent-lab.png', rpm / 'SOURCES/android-agent-lab.png'):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(asar_file(asar, 'app/icon.png'))
    copy(bundles['x64'] / 'resources/runtime/LICENSE', source / 'LICENSE')
    for record in archives.values():
        for directory in (source / 'prebuilt', rpm / 'SOURCES', output / 'aur'):
            copy(assets / record['name'], directory / record['name'])
    checks = ''.join(f"{r['sha256']}  {r['name']}\n" for r in archives.values())
    (source / 'prebuilt/SHA256SUMS').write_text(checks)
    (rpm / 'SOURCES/SHA256SUMS').write_text(checks)
    # Reproducible orig tarballs: retries of a new upstream version use identical bytes.
    def normalize(info):
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = ''
        info.mode = 0o755 if info.isdir() or info.name.endswith('/common/android-agent-lab') else 0o644
        return info
    with (output / 'ppa' / f'android-agent-lab_{version}.orig.tar.gz').open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, filename='', mode='wb', mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode='w') as tar:
                tar.add(source, arcname=source.name, filter=normalize)
    shutil.copytree(root / 'packaging/debian', source / 'debian')
    copy(root / 'packaging/common/android-agent-lab.apparmor', source / 'debian/android-agent-lab.apparmor')
    (source / 'debian/rules').chmod(0o755)
    date = format_datetime(datetime.now(timezone.utc))
    (source / 'debian/changelog').write_text(f'''android-agent-lab ({ppa_version(version)}) noble; urgency=medium

  * Package the verified Android Agent Lab {version} desktop and runtime resources.

 -- Hashim Karim <hashimkarim168@gmail.com>  {date}
''')
    manifest = dict(tag=tag, version=version, archives=archives, bundles={a:str(b.relative_to(output)) for a,b in bundles.items()}, ppaVersion=ppa_version(version))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Validated {tag}; package inputs are in {output}')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', help='Existing stable release; defaults to desktop/package.json version')
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.tag or 'v' + json.loads((ROOT / 'desktop/package.json').read_text())['version'], args.assets, args.output)


if __name__ == '__main__':
    main()
