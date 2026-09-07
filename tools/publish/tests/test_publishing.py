import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_distribution as prepare


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/publish/scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publication = load('publication-state')
release = load('release-info')
recipe = load('recipe-version')


def asar(version):
    package = json.dumps({'version': version}).encode()
    icon = b'PNG fixture'
    header = json.dumps({'files': {
        'package.json': {'size':len(package), 'offset':'0'},
        'app': {'files': {'icon.png': {'size':len(icon), 'offset':str(len(package))}}}
    }}).encode()
    return struct.pack('<IIII', 4, 8 + len(header), 4 + len(header), len(header)) + header + package + icon


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()

    def archive(self, arch='x64', *, version='9.8.7', omit=None, extra=None, machine=None, app_version=None, changed=None):
        name = f'Android-Agent-Lab-{version}-{arch}'
        dest = self.assets / (name + '.tar.gz')
        with tarfile.open(dest, 'w:gz') as tar:
            for path in prepare.REQUIRED:
                if path == omit:
                    continue
                member = tarfile.TarInfo(name + '/' + path)
                member.mode = 0o755 if path in ('android-agent-lab','chrome-sandbox') else 0o644
                data = (path + '\n').encode()
                if member.mode == 0o755:
                    data = b'\x7fELF\x02\x01' + b'\0' * 12 + struct.pack('<H', machine or {'x64':62, 'arm64':183}[arch])
                elif path == 'resources/app.asar':
                    data = asar(app_version or version)
                if path == changed:
                    data += b'changed'
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
            if extra:
                tar.addfile(extra, io.BytesIO(b'x' * extra.size))
        sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.assets.glob('*.tar.gz')}
        (self.assets / 'SHA256SUMS').write_text(''.join(f'{sha}  {name}\n' for name,sha in sums.items()))
        return dest

    def unpack(self):
        return prepare.unpack(self.assets, '9.8.7', 'x64', self.root / 'extracted', prepare.checksums(self.assets))

    def stage(self, name='prepared'):
        with contextlib.redirect_stdout(io.StringIO()):
            return prepare.prepare('v9.8.7', self.assets, self.root / name)

    def test_stable_tags_only(self):
        self.assertEqual('1.2.3', prepare.stable_version('v1.2.3'))
        for tag in ['1.2.3', 'v01.2.3', 'v1.2.3-beta.1', 'v1.2.3+build', 'v1.2.3;echo bad', 'v1.2.3\n']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                prepare.stable_version(tag)

    def test_checksum_verified_before_extraction(self):
        dest = self.archive()
        dest.write_bytes(dest.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
            self.unpack()
        self.assertFalse((self.root / 'extracted').exists())

    def test_checksum_duplicates_and_paths_rejected(self):
        self.archive()
        original = (self.assets / 'SHA256SUMS').read_text()
        for text in [original + original, '0' * 64 + '  ../escape\n']:
            (self.assets / 'SHA256SUMS').write_text(text)
            with self.assertRaises(ValueError):
                prepare.checksums(self.assets)

    def test_archive_traversal_links_devices_and_duplicates_rejected(self):
        prefix = 'Android-Agent-Lab-9.8.7-x64/'
        cases = [('..', tarfile.REGTYPE), ('/tmp/escape',tarfile.REGTYPE),
                 (prefix + '../escape',tarfile.REGTYPE), (prefix + './alias',tarfile.REGTYPE),
                 (prefix + 'link',tarfile.SYMTYPE), (prefix + 'hardlink',tarfile.LNKTYPE),
                 (prefix + 'device',tarfile.CHRTYPE), (prefix + 'android-agent-lab',tarfile.REGTYPE)]
        for name, kind in cases:
            with self.subTest(name=name):
                extra = tarfile.TarInfo(name)
                extra.type, extra.linkname = kind, '/tmp/outside'
                self.archive(extra=extra)
                with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
                    self.unpack()
                self.assertFalse((self.root / 'extracted').exists())

    def test_wrong_architecture_rejected(self):
        self.archive(machine=183)
        with self.assertRaisesRegex(ValueError, 'Wrong architecture'):
            self.unpack()

    def test_missing_runtime_rejected(self):
        self.archive(omit='resources/runtime/skills/adb-coordination/SKILL.md')
        with self.assertRaisesRegex(ValueError, 'Missing runtime'):
            self.unpack()

    def test_different_architecture_app_code_rejected(self):
        self.archive()
        self.archive('arm64', changed='resources/runtime/viewer/server.mjs')
        with self.assertRaisesRegex(ValueError, 'archives disagree'):
            self.stage()

    def test_app_version_must_match_tag(self):
        for arch in ['x64','arm64']:
            self.archive(arch, app_version='9.8.6')
        with self.assertRaisesRegex(ValueError, 'App version'):
            self.stage()

    def test_recipes_derive_version_and_hashes_from_release(self):
        self.archive(); self.archive('arm64')
        manifest = self.stage()
        dest = self.root / 'prepared'
        self.assertIn('pkgver=9.8.7', (dest / 'aur/PKGBUILD').read_text())
        formula = (dest / 'homebrew/Formula/android-agent-lab.rb').read_text()
        self.assertIn('version "9.8.7"', formula)
        for arch in ['x64','arm64']:
            self.assertIn(manifest['archives'][arch]['sha256'], formula)
        self.assertIn('Version:        9.8.7', (dest / 'rpm/SPECS/android-agent-lab.spec').read_text())
        for recipe_path in ['aur/PKGBUILD', 'homebrew/Formula/android-agent-lab.rb',
                            'rpm/SPECS/android-agent-lab.spec',
                            'ppa/android-agent-lab-9.8.7/debian/control',
                            'ppa/android-agent-lab-9.8.7/debian/copyright']:
            with self.subTest(recipe=recipe_path):
                content = (dest / recipe_path).read_text()
                self.assertIn('https://github.com/hashimkarim/android-agent-lab', content)
                self.assertNotIn('github.com/Hashim-K/', content)
        self.assertEqual((dest / 'rpm/SOURCES/android-agent-lab.png').read_bytes(), b'PNG fixture')
        self.assertIn('(9.8.7-1ppa1) noble;', (dest / 'ppa/android-agent-lab-9.8.7/debian/changelog').read_text())
        with self.assertRaises(FileExistsError):
            self.stage()

    def test_repeated_orig_is_identical_and_contains_complete_source(self):
        self.archive(); self.archive('arm64')
        self.stage('first'); self.stage('second')
        orig = 'ppa/android-agent-lab_9.8.7.orig.tar.gz'
        self.assertEqual((self.root / 'first' / orig).read_bytes(), (self.root / 'second' / orig).read_bytes())
        with tarfile.open(self.root / 'first' / orig) as tar:
            names = tar.getnames()
            self.assertIn('android-agent-lab-9.8.7/prebuilt/Android-Agent-Lab-9.8.7-arm64.tar.gz', names)
            self.assertIn('android-agent-lab-9.8.7/packaging/common/android-agent-lab', names)
            self.assertNotIn('android-agent-lab-9.8.7/debian', names)
            self.assertTrue(all(p.mtime == 0 and p.uid == p.gid == 0 for p in tar.getmembers()))


class PublicationTests(unittest.TestCase):
    def source(self, status='Published', version='0.3.1-1ppa1'):
        return {'distro_series_link':publication.SERIES, 'source_package_version':version,
                'status':status, 'date_created':'2026-09-06', 'self_link':publication.PPA + '/+sourcepub/1'}

    def test_copr_existing_failed_pending_and_missing(self):
        for state, expected in [('succeeded','done'),('failed','failed'),('running','pending')]:
            rows = {'items':[{'id':1, 'source_package':{'version':'0.3.1-1'}, 'state':state}]}
            with self.subTest(state=state), patch.object(publication,'get',return_value=rows):
                self.assertEqual(expected, publication.state('copr','0.3.1'))
        with patch.object(publication,'get',return_value={'items':[]}):
            self.assertEqual('missing', publication.state('copr','0.3.1'))
        with patch.object(publication,'get',return_value={'items':[{'state':'importing','source_package':None}]}):
            self.assertEqual('pending', publication.state('copr','0.3.1'))

    def test_copr_newer_version_never_downgraded(self):
        with patch.object(publication,'get',return_value={'items':[{'source_package':{'version':'0.4.0-1'}}]}):
            with self.assertRaisesRegex(RuntimeError, 'downgrade'):
                publication.state('copr','0.3.1')

    def test_ppa_waits_for_binary_publication(self):
        builds = [{'buildstate':'Successfully built','distro_series_link':publication.SERIES,'arch_tag':'amd64'}]
        binary = {'binary_package_version':'0.3.1-1ppa1','distro_arch_series_link':publication.SERIES + '/amd64'}
        for rows, expected in [([], 'pending'), ([binary], 'done')]:
            with patch.object(publication,'entries',side_effect=[[self.source()],builds,rows]):
                self.assertEqual(expected, publication.state('ppa','0.3.1'))

    def test_ppa_failure_requires_retry_not_duplicate_upload(self):
        with patch.object(publication,'entries',side_effect=[[self.source()],[{'buildstate':'Failed to build'}]]):
            with self.assertRaisesRegex(RuntimeError,'Retry that build'):
                publication.state('ppa','0.3.1')

    def test_ppa_used_or_newer_version_never_uploaded_again(self):
        for source in [self.source('Deleted'), self.source(version='0.3.1-1ppa2'), self.source(version='0.4.0-1ppa1')]:
            with patch.object(publication,'entries',return_value=[source]):
                with self.assertRaises(RuntimeError):
                    publication.state('ppa','0.3.1')

    def test_ppa_missing_and_old_packaging_revision(self):
        with patch.object(publication,'entries',return_value=[]):
            self.assertEqual('missing', publication.state('ppa','0.3.1'))
        self.assertEqual('0.2.0-1ppa2', prepare.ppa_version('0.2.0'))

    def test_api_errors_are_not_absence(self):
        for platform in ['copr','ppa']:
            with patch.object(publication,'get',side_effect=TimeoutError('API unavailable')):
                with self.assertRaises(TimeoutError):
                    publication.state(platform,'0.3.1')

    def test_pagination_and_polling_revalidate_cache(self):
        with patch.object(publication,'get',side_effect=[{'entries':[1],'next_collection_link':publication.PPA + '?page=2'}, {'entries':[2]}]):
            self.assertEqual([1,2], publication.entries(publication.PPA))
        with patch.object(publication,'get',return_value={'entries':[],'next_collection_link':'https://example.org/'}):
            with self.assertRaises(RuntimeError): publication.entries(publication.PPA)
        with patch('urllib.request.urlopen', return_value=contextlib.nullcontext(io.StringIO('{}'))) as request:
            publication.get(publication.PPA)
            self.assertEqual('no-cache', request.call_args.args[0].get_header('Cache-control'))
            self.assertEqual(30, request.call_args.kwargs['timeout'])

    def test_remote_wait_is_bounded_and_never_resubmits(self):
        with patch.object(sys,'argv',['publication-state.py','ppa','0.3.1','--wait']), \
             patch.object(publication,'state',return_value='missing'), \
             patch.object(publication.time,'monotonic',side_effect=[0,2701]), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'Timed out'):
                publication.main()


class ReleaseTests(unittest.TestCase):
    def test_release_api_uses_canonical_repository(self):
        with patch('urllib.request.urlopen', return_value=contextlib.nullcontext(io.StringIO('{}'))) as request:
            release.get('releases/latest')
            self.assertEqual(request.call_args.args[0].full_url,
                             'https://api.github.com/repos/hashimkarim/android-agent-lab/releases/latest')

    def metadata(self, **overrides):
        result = dict(tag_name='v0.3.1', draft=False, prerelease=False, assets=[{'name':name} for name in [
            'SHA256SUMS','Android-Agent-Lab-0.3.1-x64.tar.gz','Android-Agent-Lab-0.3.1-arm64.tar.gz']])
        return result | overrides

    def test_published_latest_stable_required(self):
        with patch.object(release,'get',side_effect=[self.metadata(), {'tag_name':'v0.3.1'}]):
            self.assertEqual('0.3.1', release.validate('v0.3.1'))
        for metadata in [self.metadata(draft=True),self.metadata(prerelease=True),self.metadata(assets=[])]:
            with patch.object(release,'get',side_effect=[metadata, {'tag_name':'v0.3.1'}]):
                with self.assertRaises(ValueError): release.validate('v0.3.1')
        with patch.object(release,'get',side_effect=[self.metadata(), {'tag_name':'v0.4.0'}]):
            with self.assertRaisesRegex(ValueError, 'latest stable'):
                release.validate('v0.3.1')

    def test_recipe_retry_noop_and_downgrade_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'recipe'
            self.assertEqual('missing',recipe.compare(path,'aur','0.3.1'))
            for platform, text in [('aur','pkgver=0.3.1\n'),('homebrew','  version "0.3.1"\n')]:
                path.write_text(text)
                self.assertEqual('done',recipe.compare(path,platform,'0.3.1'))
                self.assertEqual('older',recipe.compare(path,platform,'0.4.0'))
                with self.assertRaisesRegex(ValueError,'downgrade'): recipe.compare(path,platform,'0.2.0')
            path.write_text('pkgver=$(do-something)\n')
            with self.assertRaisesRegex(ValueError, 'refusing to guess'):
                recipe.compare(path,'aur','0.3.1')

    def test_production_requires_platform_secret_before_docker(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'manifest.json').write_text('{"tag":"v0.3.1"}')
            env = {k:v for k,v in os.environ.items() if k not in ['AUR_SSH_PRIVATE_KEY','COPR_CONFIG','HOMEBREW_SSH_PRIVATE_KEY','PPA_GPG_PRIVATE_KEY']}
            env.update(DRY_RUN='false', RELEASE_TAG='v0.3.1')
            for platform, secret in [('aur','AUR_SSH_PRIVATE_KEY'),('homebrew','HOMEBREW_SSH_PRIVATE_KEY'),('copr','COPR_CONFIG'),('ppa','PPA_GPG_PRIVATE_KEY')]:
                result = subprocess.run(['bash',str(ROOT / 'tools/publish/scripts/publish-platform.sh'),platform,temp], env=env, text=True, capture_output=True)
                self.assertNotEqual(0,result.returncode)
                self.assertIn('Missing repository secret/variable ' + secret,result.stdout)

    def test_homebrew_publisher_accepts_only_the_renamed_tap(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'manifest.json').write_text('{"tag":"v0.3.1"}')
            commands = path / 'commands.log'
            commands.touch()
            tools = path / 'bin'
            tools.mkdir()
            # Exercise the publisher without containers, network calls or real keys.
            stubs = {
                'docker': 'exit 0\n',
                'python3': 'case "$1" in */recipe-version.py) exit 10 ;; esac\n',
                'git': 'printf "%s\\n" "$*" >> "$COMMAND_LOG"\n'
                       'if [ "$1" = clone ]; then mkdir -p "$3"; fi\n',
            }
            for name, body in stubs.items():
                command = tools / name
                command.write_text('#!/bin/sh\nset -eu\n' + body)
                command.chmod(0o755)
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith('HOMEBREW_') and key != 'GITHUB_STEP_SUMMARY'}
            env.update(PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       DRY_RUN='false', RELEASE_TAG='v0.3.1',
                       HOMEBREW_SSH_PRIVATE_KEY='test key', COMMAND_LOG=str(commands))
            for tap, accepted in [('hashimkarim/homebrew-tap', True),
                                  ('Hashim-K/homebrew-tap', False),
                                  ('someone-else/homebrew-tap', False)]:
                with self.subTest(tap=tap):
                    commands.write_text('')
                    result = subprocess.run(
                        ['bash', str(ROOT / 'tools/publish/scripts/publish-platform.sh'),
                         'homebrew', temp], env=env | {'HOMEBREW_TAP_REPOSITORY': tap},
                        text=True, capture_output=True, timeout=10)
                    if accepted:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn('clone git@github.com:hashimkarim/homebrew-tap.git ',
                                      commands.read_text())
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('Unexpected Homebrew destination', result.stderr)
                        self.assertEqual(commands.read_text(), '')


if __name__ == '__main__':
    unittest.main()
