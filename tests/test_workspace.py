"""Workspace persistence, discovery, isolation and bounded project operations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workspace as ws
import desktop_jobs as jobs
import desktop_rpc


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lab = self.root / 'legacy-lab'
        self.lab.mkdir()
        self.env = patch.dict(os.environ, {'ADB_LAB_WORKSPACE': str(self.root / 'workspace'),
            'ADB_COORD_STATE': str(self.root / 'claims'), 'ADB_SERVER_SOCKET': 'tcp:localhost:5037'})
        self.env.start()
        self.addCleanup(self.env.stop)
        patcher = patch.object(ws.lab, 'ROOT', self.lab)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_separate_emulators_keep_unique_ports_names_and_compose_identity(self):
        first = ws.create_emulator('Personal test')
        second = ws.create_emulator('Agent test')
        self.assertNotEqual(first['project'], second['project'])
        self.assertEqual(len({first['adbPort'], first['webPort'], second['adbPort'], second['webPort']}), 4)
        self.assertNotEqual(first['root'], second['root'])
        ws.rename('emulators', second['id'], 'Checkout tests')
        with ws.inventory() as data:
            self.assertEqual(len(data['emulators']), 2)
            self.assertEqual(data['emulators'][1]['name'], 'Checkout tests')
            self.assertEqual(ws.public_inventory(data)['emulators'][0]['serial'], f"127.0.0.1:{first['adbPort']}")
        self.assertEqual((ws.home() / 'workspace.json').stat().st_mode & 0o777, 0o600)

    def test_old_single_emulator_is_adopted_without_resetting_data(self):
        (self.lab / '.env').write_text('ADB_PORT=15555\nWEB_PORT=8765\nVNC_PASSWORD=abcd1234\n')
        with ws.inventory() as data:
            row = data['emulators'][0]
            self.assertEqual(row['id'], 'legacy')
            self.assertEqual(row['project'], 'android-agent-lab')
            self.assertEqual(row['root'], str(self.lab))
        with ws.inventory() as data:
            self.assertEqual(len(data['emulators']), 1)

    def test_wireless_discovery_uses_tls_services_and_pairing_secret_is_stdin(self):
        output = 'List of discovered mdns services\nadb-abc _adb-tls-connect._tcp. 192.168.1.8:40000\nstudio-test _adb-tls-pairing._tcp 192.168.1.8:40001\nold _adb._tcp 192.168.1.8:5555\nbad _adb-tls-pairing._tcp --help\n'
        found = ws.parse_services(output)
        self.assertEqual([s['kind'] for s in found], ['connect', 'pairing'])
        with patch.object(ws, 'adb', return_value='Successfully paired to host') as adb:
            ws.pair(found[1]['address'], '123456')
            self.assertEqual(adb.call_args.args, ('pair', '192.168.1.8:40001'))
            self.assertEqual(adb.call_args.kwargs['input'], '123456\n')
        for value in ['--help', 'localhost;evil:5555', '192.168.1.8:0', '192.168.1.8:70000']:
            with self.assertRaises(ValueError):
                ws.endpoint(value)
        self.assertEqual(ws.endpoint('[::1]:5555'), '[::1]:5555')

    def test_usb_discovery_and_names_survive_unplugging_without_executing_device_commands(self):
        ws.rename('device', 'phone-123', 'My phone')
        with ws.inventory() as data:
            found = ws.devices('List of devices attached\nphone-123 unauthorized usb:1-2 model:Pixel_9 transport_id:1\n', data)
            self.assertEqual(found[0]['name'], 'My phone')
            self.assertEqual(found[0]['transport'], 'USB')
            self.assertEqual(found[0]['state'], 'unauthorized')
            self.assertEqual(ws.devices('', data)[0]['state'], 'disconnected')

    def test_avahi_fallback_resolves_changed_ports_and_ipv6_without_resetting_adb(self):
        sample = (r'=;wlo1;IPv4;adb-watch\032\0402\041;_adb-tls-connect._tcp;local;Android.local;192.168.1.159;43443;' + '\n' +
                  '=;wlo1;IPv6;adb-watch;_adb-tls-connect._tcp;local;Android.local;fd00::159;43443;\n')
        def browse(args, **kwargs):
            self.assertNotIn('--ipv4', args)  # avahi-browse 0.8 has no such option.
            if args[-1] == '_adb-tls-pairing._tcp':
                return subprocess.CompletedProcess(args, 0, '', '')
            raise subprocess.TimeoutExpired(args, 5, output=sample.encode())
        with patch.object(ws, 'adb', side_effect=ws.coord.CoordinationError('mdns is not supported')) as adb, \
             patch.object(ws.shutil, 'which', return_value='/usr/bin/avahi-browse'), patch.object(ws.subprocess, 'run', side_effect=browse):
            result = ws.discover()
        self.assertTrue(result['available'])
        self.assertEqual(result['backend'], 'avahi')
        self.assertEqual(result['services'][0], dict(name='adb-watch (2)', kind='connect', address='192.168.1.159:43443'))
        self.assertEqual(result['services'][1]['address'], '[fd00::159]:43443')
        adb.assert_called_once_with('mdns', 'services')

    def test_unavailable_mdns_keeps_manual_pairing_and_connecting_usable(self):
        with patch.object(ws, 'adb', side_effect=ws.coord.CoordinationError('mdns is not supported')), \
             patch.object(ws.shutil, 'which', return_value=None):
            result = ws.discover()
        self.assertFalse(result['available'])
        self.assertIn('manual IP/port', result['message'])
        with patch.object(ws, 'adb', return_value='Successfully paired to 192.168.1.159:40000 [guid=adb-watch]'):
            self.assertEqual(ws.pair('192.168.1.159:40000', '123456')['guid'], 'adb-watch')
        with patch.object(ws, 'adb', return_value='connected to 192.168.1.159:43443') as adb:
            self.assertIn('connected', ws.connect('192.168.1.159:43443')['message'])
            adb.assert_called_once_with('connect', '192.168.1.159:43443', timeout=8)
        with patch.object(ws, 'adb', side_effect=subprocess.TimeoutExpired('adb', 8)):
            with self.assertRaisesRegex(ws.coord.CoordinationError, 'current IP and connection port'):
                ws.connect('192.168.1.159:43443')

    def test_avahi_can_flush_resolved_devices_after_its_five_second_resolver_timeout(self):
        binary = self.root / 'avahi-browse'
        binary.write_text('#!' + sys.executable + '\nimport sys,time\n'
            'if sys.argv[-1] == "_adb-tls-connect._tcp":\n'
            ' print("=;wlo1;IPv4;adb-watch;_adb-tls-connect._tcp;local;Android.local;192.168.1.159;36879;")\n'
            ' time.sleep(5.15)\n')
        binary.chmod(0o700)
        with patch.object(ws, 'adb', side_effect=ws.coord.CoordinationError('mdns is not supported')), \
             patch.object(ws.shutil, 'which', return_value=str(binary)):
            result = ws.discover()
        self.assertTrue(result['available'])
        self.assertEqual([s['address'] for s in result['services']], ['192.168.1.159:36879'])

    def test_remote_adb_discovery_never_uses_the_laptops_avahi(self):
        with patch.dict(os.environ, {'ADB_SERVER_SOCKET': 'tcp:remote-host:5037'}), \
             patch.object(ws, 'adb', side_effect=ws.coord.CoordinationError('unsupported')), \
             patch.object(ws.shutil, 'which', return_value='/usr/bin/avahi-browse'), patch.object(ws.subprocess, 'run') as run:
            self.assertFalse(ws.discover()['available'])
            run.assert_not_called()

    def test_network_prefixes_prefer_the_default_lan_and_exclude_virtual_interfaces(self):
        def interface(name, address):
            return dict(ifname=name, operstate='UP', addr_info=[dict(family='inet', scope='global', local=address, prefixlen=24)])
        addresses = [interface('enp2s0', '192.168.44.1'), interface('wlo1', '192.168.1.51'),
                     interface('docker0', '172.17.0.1'), interface('tailscale0', '100.64.0.1'), interface('br-test', '172.20.0.1')]
        with patch.object(ws.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0, json.dumps(addresses)),
                subprocess.CompletedProcess([], 0, '[{"dev":"wlo1","metric":600}]')]):
            rows = ws.networks()['networks']
        self.assertEqual([r['prefix'] for r in rows], ['192.168.1.', '192.168.44.'])
        self.assertEqual(rows[0]['kind'], 'Wi-Fi')
        self.assertTrue(rows[0]['preferred'])

    def test_library_discovers_project_apks_without_building_or_following_external_paths(self):
        root = self.root / 'project'
        output = root / 'app/build/outputs/apk/debug/app.apk'
        output.parent.mkdir(parents=True)
        output.write_bytes(b'local-apk')
        (root / 'gradlew').write_text('#!/bin/sh\ntouch SHOULD_NOT_BUILD\n')
        project = ws.save_project({'path': str(root), 'name': 'Local app'})
        outside = self.root / 'outside.apk'; outside.write_bytes(b'outside')
        (output.parent / 'linked.apk').symlink_to(outside)
        ignored = root / 'node_modules/dependency/build/outputs/apk/dependency.apk'
        ignored.parent.mkdir(parents=True); ignored.write_bytes(b'ignore')
        result = ws.library()
        self.assertEqual([o['path'] for o in result['projects'][0]['outputs']], ['app/build/outputs/apk/debug/app.apk'])
        self.assertFalse((root / 'SHOULD_NOT_BUILD').exists())
        with patch.object(jobs, 'install', return_value={'message': 'Installed'}) as install:
            jobs.dispatch(dict(action='installOutput', id=project['id'], serial='selected-watch', output='app/build/outputs/apk/debug/app.apk'))
            self.assertEqual(install.call_args.args[1], 'selected-watch')
            self.assertEqual(Path(install.call_args.args[0]['path']).read_bytes(), b'local-apk')
            for path in ['../outside.apk', 'app/build/outputs/apk/debug/linked.apk', 'missing.apk']:
                with self.assertRaisesRegex(ValueError, 'no longer available'):
                    jobs.dispatch(dict(action='installOutput', id=project['id'], serial='selected-watch', output=path))
            self.assertEqual(install.call_count, 1)

    def test_reservation_revokes_agents_survives_restart_and_requires_explicit_unlock(self):
        serial = 'test-device'
        first = ws.coord.claim(serial, 'human:test', str(self.root), ttl=1)
        locked = ws.reservation(serial, True, first['token'])
        self.assertNotEqual(locked['token'], first['token'])
        with self.assertRaises(ws.coord.CoordinationError):
            ws.coord.check_owner(locked, first['token'])
        with self.assertRaises(ws.coord.CoordinationError):
            ws.coord.claim(serial, 'codex:other', str(self.root), reclaim=True)
        with self.assertRaises(ws.coord.CoordinationError):
            ws.coord.change_claim(serial, locked['token'], 'release')
        renewed = ws.coord.change_claim(serial, locked['token'], 'renew')
        self.assertEqual(renewed['expires_at'], 2**40)
        self.assertEqual(ws.reservation_token(serial), locked['token'])
        with ws.inventory() as data:
            public = ws.public_inventory(data)
            self.assertNotIn(locked['token'], json.dumps(public))
        unlocked = ws.reservation(serial, False)
        self.assertNotEqual(unlocked['token'], locked['token'])
        ws.coord.change_claim(serial, unlocked['token'], 'release')
        self.assertIsNone(ws.reservation_token(serial))

    def test_disconnected_reserved_devices_remain_unlockable(self):
        record = ws.reservation('unplugged-phone', True)
        with ws.inventory() as data:
            found = ws.devices('', data)
        self.assertEqual(found[0]['serial'], 'unplugged-phone')
        self.assertTrue(found[0]['lockedHere'])
        self.assertEqual(found[0]['state'], 'disconnected')
        ws.reservation('unplugged-phone', False)

    def test_job_progress_checks_ownership_without_competing_with_install_or_renewing(self):
        claim = ws.coord.claim('job-phone', 'human:desktop', str(self.root))
        data = dict(serial='job-phone', token=claim['token'])
        with ws.coord.locked('job-phone'):
            result = desktop_rpc.dispatch(dict(action='checkSession', **data))
            self.assertEqual(result['expires_at'], claim['expires_at'])
            self.assertNotIn('token', result)
            with self.assertRaisesRegex(ws.coord.CoordinationError, 'operation in progress'):
                desktop_rpc.dispatch(dict(action='check', **data))
        ws.coord.change_claim('job-phone', claim['token'], 'handoff', 'codex:next')
        with self.assertRaises(ws.coord.CoordinationError):
            desktop_rpc.dispatch(dict(action='checkSession', **data))

    def test_expired_reservation_takeover_is_explicit_and_never_overrides_live_claim(self):
        record = ws.coord.claim('old-device', 'codex:old', str(self.root))
        record['expires_at'] = 1
        ws.coord.save_record(ws.coord.record_path('old-device'), record)
        with self.assertRaises(ws.coord.CoordinationError):
            ws.reservation('old-device', True)
        locked = ws.reservation('old-device', True, reclaim=True)
        self.assertTrue(locked['reserved'])
        with self.assertRaises(ws.coord.CoordinationError):
            ws.coord.claim('old-device', 'codex:next', str(self.root), reclaim=True)

    def test_lifecycle_cannot_touch_another_claim_and_deletion_is_scoped(self):
        first, second = ws.create_emulator('First'), ws.create_emulator('Second')
        serial = f"127.0.0.1:{first['adbPort']}"
        claim = ws.coord.claim(serial, 'codex:other', str(self.root))
        with patch.object(jobs, 'run') as run:
            with self.assertRaises(ws.coord.CoordinationError):
                jobs.emulator(first['id'], 'delete')
            run.assert_not_called()
        ws.coord.change_claim(serial, claim['token'], 'release')
        with patch.object(jobs, 'run') as run:
            jobs.emulator(first['id'], 'delete')
            argv = run.call_args.args[0]
            self.assertIn(first['project'], argv)
            self.assertNotIn(second['project'], argv)
            self.assertEqual(argv[-2:], ['down', '--volumes'])
        self.assertTrue(Path(second['root']).is_dir())
        with ws.inventory() as data:
            self.assertEqual([e['id'] for e in data['emulators']], [second['id']])

    def test_project_build_uses_literal_paths_and_saved_apk_is_independent(self):
        root = self.root / 'app $(touch SHOULD_NOT_EXIST)'
        root.mkdir()
        (root / 'gradlew').write_text('#!/bin/sh\nmkdir -p app/build/outputs/apk/debug\nprintf apk > app/build/outputs/apk/debug/app-debug.apk\n')
        project = ws.save_project({'path': str(root), 'name': 'Test app', 'package': 'com.example.app'})
        for task in ['--help', 'assembleDebug; touch bad', 'assembleDebug otherTask']:
            with self.assertRaises(ValueError):
                ws.save_project({'path': str(root), 'task': task})
        result = jobs.build(project)
        saved = Path(result['apks'][0]['path'])
        original = root / 'app/build/outputs/apk/debug/app-debug.apk'
        original.write_text('changed')
        self.assertEqual(saved.read_text(), 'apk')
        self.assertFalse((self.root / 'SHOULD_NOT_EXIST').exists())
        ws.forget('apks', result['apks'][0]['id'])
        self.assertTrue(original.is_file())
        self.assertFalse(saved.exists())
        ws.forget('projects', project['id'])
        self.assertTrue(root.is_dir())

    def test_open_project_reuses_canonical_path_and_preserves_custom_settings(self):
        root = self.root / 'My app'
        root.mkdir()
        (root / 'gradlew').write_text('#!/bin/sh\ntouch SHOULD_NOT_RUN\n')
        saved = ws.save_project({'path': str(root), 'name': 'Checkout', 'task': ':app:assembleDemoDebug',
            'apk': 'app/build/outputs/apk/demo/debug/app.apk', 'package': 'com.example.demo'})
        alias = self.root / 'symlink'
        alias.symlink_to(root)
        result = desktop_rpc.dispatch({'action': 'openProject', 'path': str(alias)})
        self.assertFalse(result['created'])
        self.assertEqual(result['project'], saved)
        with ws.inventory() as data:
            self.assertEqual(data['projects'], [saved])
        self.assertFalse((root / 'SHOULD_NOT_RUN').exists())

    def test_concurrent_project_opens_create_one_entry_without_running_gradle(self):
        root = self.root / 'Android project'
        root.mkdir()
        (root / 'gradlew').write_text('#!/bin/sh\nexit 99\n')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(ws.open_project, [str(root)] * 8))
        self.assertEqual(sum(r['created'] for r in results), 1)
        self.assertEqual(len({r['project']['id'] for r in results}), 1)
        self.assertEqual(results[0]['project']['task'], 'assembleDebug')
        with ws.inventory() as data:
            self.assertEqual(len(data['projects']), 1)
            self.assertEqual(data['apks'], [])

    def test_open_project_rejects_missing_paths_files_and_non_gradle_roots(self):
        for target in [self.root / 'missing', self.root]:
            with self.assertRaises((OSError, ValueError)):
                ws.open_project(str(target))
        (self.root / 'gradlew').write_text('wrapper')
        with self.assertRaises(ValueError):
            ws.open_project(str(self.root / 'gradlew'))
        self.assertFalse((ws.home() / 'workspace.json').exists())

    def test_ambiguous_build_outputs_are_never_installed_automatically(self):
        root = self.root / 'project'
        (root / 'app/build/outputs/apk/debug').mkdir(parents=True)
        (root / 'gradlew').write_text('#!/bin/sh\nexit 0\n')
        for filename in ('one.apk', 'two.apk'):
            (root / 'app/build/outputs/apk/debug' / filename).write_text('apk')
        project = ws.save_project({'path': str(root)})
        with patch.object(jobs, 'install') as install:
            with self.assertRaisesRegex(ValueError, 'More than one APK'):
                jobs.build(project, 'device', 'token')
            install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
