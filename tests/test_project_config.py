"""Project discovery and actual build environment selection without a live device."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import project_config as config
import desktop_jobs as jobs
import workspace as ws


class ProjectConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'repo with spaces'
        self.project.mkdir()
        self.write('gradlew', '#!/bin/sh\nexit 99\n')
        self.write('gradle/wrapper/gradle-wrapper.properties', 'distributionUrl=https\\://services.gradle.org/distributions/gradle-9.6.1-bin.zip\n')
        self.write('settings.gradle.kts', 'rootProject.name = "Detected App"\ninclude(":app")\n')
        self.write('build.gradle.kts', 'plugins { id("com.android.application") version "9.2.1" apply false }\n')
        self.write('app/build.gradle.kts', 'plugins { id("com.android.application") }\nandroid {\n defaultConfig {\n applicationId = "com.example.app"\n }\n}\n')
        self.sdk = self.root / 'SDK'
        (self.sdk / 'platform-tools').mkdir(parents=True)
        self.jdks = [self.make_jdk(major) for major in (11, 17, 21, 25)]
        env = patch.dict(os.environ, {'JAVA_HOME': self.jdks[0]['path'], 'ANDROID_HOME': str(self.sdk),
            'GRADLE_USER_HOME': str(self.root / 'gradle-home'), 'ADB_LAB_WORKSPACE': str(self.root / 'workspace')})
        env.start(); self.addCleanup(env.stop)
        installed = patch.object(config, 'installed_jdks', return_value=self.jdks)
        installed.start(); self.addCleanup(installed.stop)

    def write(self, name, value):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def make_jdk(self, major):
        root = self.root / f'jdk-{major}'
        (root / 'bin').mkdir(parents=True)
        (root / 'release').write_text(f'JAVA_VERSION="{major}.0.1"\n')
        for tool in ('java', 'javac'):
            (root / 'bin' / tool).write_text('#!/bin/sh\nexit 0\n')
            (root / 'bin' / tool).chmod(0o700)
        return dict(path=str(root), version=major)

    def metadata(self, variant='debug', package='com.example.app', elements=None):
        elements = elements or [dict(outputFile='app.apk', filters=[])]
        for item in elements:
            if '..' not in Path(item['outputFile']).parts:
                self.write(f'app/build/outputs/apk/{variant}/{item["outputFile"]}', 'apk')
        return self.write(f'app/build/outputs/apk/{variant}/output-metadata.json', json.dumps(dict(
            artifactType={'type': 'APK'}, applicationId=package, variantName=variant, elements=elements)))

    def test_detects_kotlin_repo_without_executing_and_replaces_incompatible_inherited_java(self):
        row = config.inspect(self.project)
        self.assertEqual((row['name'], row['task'], row['package']), ('Detected App', ':app:assembleDebug', 'com.example.app'))
        self.assertEqual((row['gradleVersion'], row['agpVersion']), ('9.6.1', '9.2.1'))
        self.assertEqual(row['javaVersion'], 17)
        self.assertEqual(row['sdkHome'], str(self.sdk))
        self.assertEqual(row['issues'], [])
        self.write('gradlew', '#!/bin/sh\nprintf "%s\\n%s\\n%s" "$JAVA_HOME" "$ANDROID_HOME" "$1" > environment-used\nmkdir -p app/build/outputs/apk/debug\nprintf apk > app/build/outputs/apk/debug/test.apk\n')
        saved = ws.save_project({'path': str(self.project)})
        jobs.build(saved)
        self.assertEqual((self.project / 'environment-used').read_text().splitlines()[:2], [self.jdks[1]['path'], str(self.sdk)])
        self.assertEqual(os.environ['JAVA_HOME'], self.jdks[0]['path'])

    def test_newer_java_is_not_selected_for_an_older_gradle(self):
        self.write('gradle/wrapper/gradle-wrapper.properties', 'distributionUrl=https\\://services.gradle.org/distributions/gradle-7.5-all.zip\n')
        self.write('build.gradle.kts', 'plugins { id("com.android.application") version "7.4.2" apply false }\n')
        with patch.dict(os.environ, {'JAVA_HOME': self.jdks[3]['path']}):
            self.assertEqual(config.inspect(self.project)['javaVersion'], 11)

    def test_explicit_jdk_and_daemon_criteria_take_priority_and_invalid_pins_explain_failure(self):
        self.write('gradle.properties', f'org.gradle.java.home={self.jdks[0]["path"]}\n')
        row = config.inspect(self.project)
        with self.assertRaisesRegex(ValueError, 'Gradle properties.*incompatible JDK'):
            config.environment(row)
        self.assertEqual(config.inspect(self.project, {'javaHome': self.jdks[2]['path']})['javaVersion'], 21)
        self.write('gradle.properties', '')
        self.write('gradle/gradle-daemon-jvm.properties', 'toolchainVersion=21\n')
        self.assertEqual(config.inspect(self.project)['javaVersion'], 21)
        self.write('gradle/gradle-daemon-jvm.properties', 'toolchainVersion=26\n')
        self.assertRegex('\n'.join(config.inspect(self.project)['issues']), 'Java 26')

    def test_gradle_properties_uses_local_sdk_and_detects_a_missing_one(self):
        self.write('local.properties', f'sdk.dir={self.sdk}\n')
        self.assertEqual(config.inspect(self.project)['sdkSource'], 'local.properties')
        with self.assertRaisesRegex(ValueError, 'local.properties sets a different sdk.dir'):
            config.environment(config.inspect(self.project, {'sdkHome': '/different/sdk'}))
        self.write('local.properties', 'sdk.dir=/missing/android/sdk\n')
        with self.assertRaisesRegex(ValueError, 'Android SDK from local.properties is missing'):
            config.environment(config.inspect(self.project))

    def test_groovy_catalog_alias_and_debug_suffix(self):
        (self.project / 'app/build.gradle.kts').unlink()
        self.write('gradle/libs.versions.toml', '[versions]\nagp = "9.2.1"\n[plugins]\nandroid-application = { id = "com.android.application", version.ref = "agp" }\n')
        self.write('build.gradle.kts', 'plugins { alias(libs.plugins.android.application) apply false }\n')
        self.write('app/build.gradle', '''plugins { alias(libs.plugins.android.application) }
android {
 defaultConfig { applicationId 'com.example.groovy' }
 buildTypes { debug { applicationIdSuffix '.dev' } }
}
''')
        self.assertEqual(config.inspect(self.project)['package'], 'com.example.groovy.dev')
        self.assertEqual(config.inspect(self.project)['task'], ':app:assembleDebug')

    def test_missing_metadata_does_not_install_an_old_release_in_a_debug_build(self):
        saved = ws.save_project({'path': str(self.project)})
        self.write('app/build/outputs/apk/release/app.apk', 'old release')
        with patch.object(jobs, 'run'), patch.object(jobs, 'install') as install:
            with self.assertRaisesRegex(ValueError, 'no APK was found'):
                jobs.build(saved, 'phone', 'token')
            install.assert_not_called()

    def test_dynamic_flavors_are_resolved_by_selected_variant_metadata_and_paths_stay_in_repo(self):
        self.write('app/build.gradle.kts', 'plugins { id("com.android.application") }\nandroid { productFlavors { create("demo") { } } }\n')
        self.assertEqual(config.inspect(self.project)['package'], '')
        self.metadata('demoDebug', 'com.example.demo')
        self.metadata('release', 'com.example.production')
        self.assertEqual(config.inspect(self.project, {'task': ':app:assembleDemoDebug'})['package'], 'com.example.demo')
        self.assertEqual(config.inspect(self.project, {'task': ':app:assembleRelease'})['package'], 'com.example.production')
        output = self.project / 'app/build/outputs/apk/demoDebug/app.apk'
        outside = self.root / 'outside.apk'; outside.write_text('outside')
        output.unlink(); output.symlink_to(outside)
        self.assertEqual(config.artifact_metadata(self.project, ':app:assembleDemoDebug'), [])

    def test_multiple_app_modules_do_not_guess_application_id(self):
        self.write('settings.gradle.kts', 'include(":app", ":wear")\n')
        self.write('wear/build.gradle.kts', 'plugins { id("com.android.application") }\nandroid { defaultConfig { applicationId = "com.example.wear" } }\n')
        self.assertEqual(config.inspect(self.project)['package'], '')
        self.assertEqual(config.inspect(self.project, {'task': ':wear:assembleDebug'})['package'], 'com.example.wear')

    def test_abi_apk_selection_uses_coordinated_device_read_and_refuses_flavor_ambiguity(self):
        self.metadata(elements=[dict(outputFile=f'{abi}.apk', filters=[dict(filterType='ABI', value=abi)]) for abi in ('armeabi-v7a', 'arm64-v8a', 'x86_64')])
        artifacts = config.artifact_metadata(self.project, ':app:assembleDebug')
        with patch.object(jobs, 'device', return_value='arm64-v8a,armeabi-v7a\n') as device:
            selected = jobs.choose_install_output(artifacts, 'phone', 'owned-token')
            self.assertTrue(selected['path'].endswith('arm64-v8a.apk'))
            device.assert_called_once_with('phone', 'owned-token', ['shell', 'getprop', 'ro.product.cpu.abilist'], timeout=15)
            artifacts[1]['variant'] = 'demoDebug'
            with self.assertRaisesRegex(ValueError, 'More than one APK'):
                jobs.choose_install_output(artifacts, 'phone', 'owned-token')


if __name__ == '__main__':
    unittest.main()
