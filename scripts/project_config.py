"""Read Gradle project hints and APK metadata; never execute a repo during discovery."""
import json
import os
from pathlib import Path
import re
import shutil


def read(path):
    try:
        with Path(path).open(encoding='utf-8', errors='replace') as stream:
            return stream.read(256_000)
    except OSError:
        return ''


def properties(path):
    result = {}
    for line in read(path).splitlines():
        match = re.match(r'\s*([^#!\s=:]+)\s*[=:]\s*(.*)', line)
        if match:
            result[match[1]] = re.sub(r'\\([\\ :=])', r'\1', match[2].strip())
    return result


def script(path):
    # Keep strings intact when removing comments (URLs may contain //).
    return re.sub(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|/\*[\s\S]*?\*/|//[^\n]*''',
                  lambda m: m[1] or '', read(path))


def literal(text, key):
    match = re.search(r'\b' + re.escape(key) + r'''\s*(?:=\s*|\(\s*|\s+)["']([^"'\n$]+)["']\s*(?=[\n;})]|$)''', text)
    return match[1] if match else ''


def block(text, key):
    match = re.search(r'\b' + re.escape(key) + r'\s*\{', text)
    if not match:
        return ''
    start, depth = match.end(), 1
    for token in re.finditer(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{}]''', text[start:]):
        if token[0] == '{':
            depth += 1
        elif token[0] == '}':
            depth -= 1
            if depth == 0:
                return text[start:start + token.start()]
    return ''


def modules(root):
    settings = script(root / 'settings.gradle.kts') or script(root / 'settings.gradle')
    paths = {':': root}
    for match in re.finditer(r'\binclude\s*(?:\(([^)]*)\)|([^\n]+))', settings):
        for name in re.findall(r'''["'](:?[\w:-]+)["']''', match[1] or match[2]):
            paths[':' + name.lstrip(':')] = root / name.strip(':').replace(':', '/')
    for match in re.finditer(r'''project\(["'](:[\w:-]+)["']\)\.projectDir\s*=\s*(?:file\(|new File\(rootDir,\s*)["']([^"']+)["']''', settings):
        paths[match[1]] = root / match[2]
    # A conventional app also works in projects with computed include statements.
    if (root / 'app').is_dir() and root / 'app' not in paths.values():
        paths[':app'] = root / 'app'
    catalog = script(root / 'gradle/libs.versions.toml')
    aliases = [re.sub(r'[-_]', '.', m[1]) for m in re.finditer(
        r'''(?m)^([\w-]+)\s*=\s*\{[^\n}]*\bid\s*=\s*["']com\.android\.application["']''', catalog)]
    found = []
    for name, path in list(paths.items())[:100]:
        path = path.resolve()
        if not path.is_relative_to(root):
            continue
        text = script(path / 'build.gradle.kts') or script(path / 'build.gradle')
        plugin = bool(re.search(r'''["']com\.android\.application["'](?![^\n]*apply\s+false)''', text))
        plugin = plugin or any(re.search(r'\balias\s*\(\s*libs\.plugins\.' + re.escape(alias) + r'\s*\)(?![^\n]*apply\s+false)', text) for alias in aliases)
        if plugin or re.search(r'\bapplicationId\s*(?:=|["\'])', text):
            found.append(dict(module=name, directory=str(path.relative_to(root)), text=text))
    return found, settings, catalog


def artifact_metadata(root, task=''):
    """Read AGP's variant/ABI/application ID output, ignoring escaping paths."""
    result = []
    candidates, _settings, _catalog = modules(root)
    if not candidates:
        candidates = [dict(module=':app', directory='app'), dict(module=':', directory='.')]
    parts = task.strip(':').split(':')
    selected = ':' + ':'.join(parts[:-1]) if len(parts) > 1 else ''
    match = re.fullmatch(r'(?:assemble|bundle)([A-Z]\w*)', parts[-1])
    variant = match[1].lower() if match else ''
    for module in candidates:
        if selected and module['module'] != selected:
            continue
        base = root / module['directory'] / 'build/outputs/apk'
        for index, path in enumerate(base.glob('**/output-metadata.json')):
            if index >= 100:
                break
            if not path.resolve().is_relative_to(root):
                continue
            try:
                data = json.loads(read(path))
                if data.get('artifactType', {}).get('type') != 'APK':
                    continue
                actual_variant = data.get('variantName', '').lower()
                if variant and not (actual_variant.endswith(variant) if variant in ('debug', 'release') else actual_variant == variant):
                    continue
                for item in data.get('elements', [])[:100]:
                    output = (path.parent / item['outputFile']).resolve()
                    if output.suffix != '.apk' or not output.is_relative_to(root) or not output.is_file():
                        continue
                    result.append(dict(path=str(output.relative_to(root)), package=data.get('applicationId', ''),
                        variant=data.get('variantName', ''), module=module['module'], filters=item.get('filters', [])))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    return list({r['path']: r for r in result}.values())


def version(value):
    match = re.match(r'(\d+)(?:\.(\d+))?', value)
    return (int(match[1]), int(match[2] or 0)) if match else (0, 0)


# https://docs.gradle.org/current/userguide/compatibility.html#java_runtime
JAVA_GRADLE = {8:(2,0), 9:(4,3), 10:(4,7), 11:(5,0), 12:(5,4), 13:(6,0), 14:(6,3),
    15:(6,7), 16:(7,0), 17:(7,3), 18:(7,5), 19:(7,6), 20:(8,3), 21:(8,5),
    22:(8,8), 23:(8,10), 24:(8,14), 25:(9,1), 26:(9,4)}


def jdk(path):
    if not path:
        return None
    root = Path(path).expanduser().resolve()
    release = properties(root / 'release').get('JAVA_VERSION', '').strip('"')
    numbers = version(release)
    major = numbers[1] if numbers[0] == 1 else numbers[0]
    if major and os.access(root / 'bin/java', os.X_OK) and os.access(root / 'bin/javac', os.X_OK):
        return dict(path=str(root), version=major)
    return None


def installed_jdks():
    candidates = [os.environ.get('JAVA_HOME')]
    java = shutil.which('java')
    if java:
        candidates.append(str(Path(java).resolve().parent.parent))
    patterns = ['/usr/lib/jvm/*', '/usr/java/*', '/opt/android-studio/jbr', '/opt/android-studio/jre',
        '/opt/android-studio*/jbr', '~/.jdks/*', '~/.sdkman/candidates/java/*',
        '~/.gradle/jdks/*', '~/android-studio/jbr', '~/.local/share/JetBrains/Toolbox/apps/android-studio/*/jbr']
    import glob
    for pattern in patterns:
        candidates.extend(glob.glob(os.path.expanduser(pattern))[:100])
    found = {}
    for candidate in candidates:
        row = jdk(candidate)
        if row:
            found.setdefault(row['path'], row)
    return list(found.values())


def toolchain(root, values, gradle, agp):
    issues = []
    minimum = 17 if version(gradle) >= (9, 0) or version(agp) >= (8, 0) else 11 if version(agp) >= (7, 0) else 8
    criteria = properties(root / 'gradle/gradle-daemon-jvm.properties')
    exact = version(criteria.get('toolchainVersion', ''))[0]
    user_properties = properties(Path(os.environ.get('GRADLE_USER_HOME', str(Path.home() / '.gradle'))) / 'gradle.properties')
    project_properties = properties(root / 'gradle.properties')
    pinned = values.get('javaHome') or user_properties.get('org.gradle.java.home') or project_properties.get('org.gradle.java.home')
    source = 'Project override' if values.get('javaHome') else 'Gradle properties' if pinned else 'Automatic'
    def compatible(row):
        return row and row['version'] >= minimum and (not exact or row['version'] == exact) and (
            not gradle or row['version'] in JAVA_GRADLE and version(gradle) >= JAVA_GRADLE[row['version']])
    found = installed_jdks()
    chosen = jdk(pinned) if pinned else None
    if pinned and not compatible(chosen):
        issues.append(f'{source} selects an unavailable or incompatible JDK: {pinned}. Choose a JDK compatible with Gradle {gradle or "in this repo"} (Java {exact or minimum}{"" if exact else "+"}).')
    if not pinned:
        preferred = properties(root / '.gradle/config.properties').get('java.home')
        chosen = jdk(preferred) if preferred else jdk(os.environ.get('JAVA_HOME'))
        if not compatible(chosen):
            chosen = next((j for j in sorted(found, key=lambda j:(j['version'] not in (8, 11, 17, 21, 25), j['version'])) if compatible(j)), None)
        if not chosen:
            issues.append(f'Install a JDK compatible with Gradle {gradle or "in this repo"}: Java {exact or minimum}{"" if exact else "+"}.')
    local_sdk = properties(root / 'local.properties').get('sdk.dir')
    sdk = local_sdk or values.get('sdkHome')
    sdk_source = 'local.properties' if local_sdk else 'Project override' if values.get('sdkHome') else 'Automatic'
    def valid_sdk(p):
        return any((p / folder).is_dir() for folder in ('platforms', 'platform-tools', 'build-tools'))
    if sdk:
        sdk = str((root / Path(sdk).expanduser()).resolve())
        if local_sdk and values.get('sdkHome') and str(Path(values['sdkHome']).expanduser().resolve()) != sdk:
            issues.append('local.properties sets a different sdk.dir. Update that file or leave the SDK override blank.')
        if not valid_sdk(Path(sdk)):
            issues.append(f'Android SDK from {sdk_source} is missing: {sdk}.')
    else:
        for candidate in [os.environ.get('ANDROID_HOME'), os.environ.get('ANDROID_SDK_ROOT'),
                          str(Path.home() / 'Android/Sdk'), '/opt/android-sdk', '/usr/lib/android-sdk']:
            if candidate and valid_sdk(Path(candidate).expanduser()):
                sdk = str(Path(candidate).expanduser().resolve())
                break
    return dict(javaHome=chosen['path'] if chosen else '', javaVersion=chosen['version'] if chosen else None,
        javaSource=source, minimumJava=minimum, sdkHome=sdk or '', sdkSource=sdk_source, issues=issues)


def inspect(root, values=None):
    root, values = Path(root).resolve(), values or {}
    found, settings, catalog = modules(root)
    wrapper = properties(root / 'gradle/wrapper/gradle-wrapper.properties').get('distributionUrl', '')
    match = re.search(r'gradle-(\d+(?:\.\d+)+)(?:-[a-zA-Z0-9.-]+)?-(?:bin|all)\.zip', wrapper)
    gradle = match[1] if match else ''
    build_text = '\n'.join([script(root / 'build.gradle.kts'), script(root / 'build.gradle'), catalog, *[m['text'] for m in found]])
    match = re.search(r'''com\.android\.tools\.build:gradle:(\d+[.\d]*)|com\.android\.application["']\)?\s+version\s+["'](\d+[.\d]*)|\bagp\s*=\s*["'](\d+[.\d]*)''', build_text)
    agp = next((g for g in match.groups() if g), '') if match else ''
    task = values.get('task') or (found[0]['module'].rstrip(':') + ':assembleDebug' if len(found) == 1 else 'assembleDebug')
    if task == ':assembleDebug':
        task = 'assembleDebug'
    selected = [m for m in found if task.startswith(m['module'] + ':')] if task.count(':') > 1 else found
    package = ''
    artifacts = artifact_metadata(root, task)
    packages = {a['package'] for a in artifacts if a['package']}
    if len(packages) == 1:
        package = packages.pop()
    elif len(selected) == 1:
        text = selected[0]['text']
        # Computed/flavored IDs need AGP output metadata, not a guessed namespace.
        default = block(text, 'defaultConfig')
        build_type = 'release' if task.endswith('Release') else 'debug' if task.endswith('Debug') else ''
        if build_type and not re.search(r'\bproductFlavors\b', text):
            package = literal(default, 'applicationId')
            suffix_block = block(block(text, 'buildTypes'), build_type)
            suffix = literal(suffix_block, 'applicationIdSuffix')
            if 'applicationIdSuffix' in suffix_block and not suffix:
                package = ''
            elif package:
                package += suffix
    if package and not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+', package, re.ASCII):
        package = ''
    config = dict(name=literal(settings, 'rootProject.name') or root.name, task=task, package=package,
        gradleVersion=gradle, agpVersion=agp, tasks=[m['module'].rstrip(':') + ':assembleDebug' for m in found],
        outputs=artifacts, **toolchain(root, values, gradle, agp))
    if not config['sdkHome'] and found:
        config['issues'].append('Android SDK not found. Install it with Android Studio, or set its path below.')
    return config


def environment(config):
    if config['issues']:
        raise ValueError('\n'.join(config['issues']))
    env = dict(os.environ)
    if config['javaHome']:
        env['JAVA_HOME'] = config['javaHome']
        env['PATH'] = str(Path(config['javaHome']) / 'bin') + os.pathsep + env.get('PATH', '')
    if config['sdkHome']:
        env['ANDROID_HOME'] = env['ANDROID_SDK_ROOT'] = config['sdkHome']
    return env
