#!/usr/bin/env python3
"""Check existing publications: 0=done, 1=submit, 2=API/build error. Never guess absence."""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from prepare_distribution import stable_version, ppa_version

OWNER = 'hashimkarim'
PACKAGE = 'android-agent-lab'
PPA = f'https://api.launchpad.net/1.0/~{OWNER}/+archive/ubuntu/{PACKAGE}'
SERIES = 'https://api.launchpad.net/1.0/ubuntu/noble'


def get(url):
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'android-agent-lab-publishing'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def entries(url):
    result = []
    for _ in range(20):
        data = get(url)
        result.extend(data['entries'])
        url = data.get('next_collection_link')
        if not url:
            return result
        if not url.startswith('https://api.launchpad.net/'):
            raise RuntimeError('Unexpected publication pagination URL')
    raise RuntimeError('Publication history exceeded the bounded query limit')


def numeric(version):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-1(?:ppa(\d+))?)?', version)
    if not match:
        raise RuntimeError(f'Unrecognized published package version: {version}')
    return tuple(int(n or 0) for n in match.groups())


def state(platform, version):
    stable_version('v' + version)
    if platform == 'copr':
        data = get(f'https://copr.fedorainfracloud.org/api_3/build/list?ownername={OWNER}&projectname={PACKAGE}&limit=100')
        known = [b for b in data['items'] if (b.get('source_package') or {}).get('version')]
        for row in known:
            if numeric(row['source_package']['version']) > numeric(version + '-1'):
                raise RuntimeError('COPR already has a newer package; refusing a downgrade')
        builds = [b for b in known if b['source_package']['version'] == version + '-1']
        if not builds:
            if any(not b.get('source_package') and b['state'] not in {'succeeded', 'failed', 'canceled', 'skipped'} for b in data['items']):
                return 'pending'
            return 'missing'
        result = max(builds, key=lambda b:b['id'])['state']
        return 'done' if result == 'succeeded' else 'failed' if result in {'failed','canceled','skipped'} else 'pending'
    query = urllib.parse.urlencode({'ws.op':'getPublishedSources', 'source_name':PACKAGE, 'exact_match':'true'})
    sources = [s for s in entries(PPA + '?' + query) if s['distro_series_link'] == SERIES]
    target = ppa_version(version)
    for source in sources:
        if numeric(source['source_package_version']) > numeric(target):
            raise RuntimeError('PPA already has a newer package; refusing a downgrade')
    sources = [s for s in sources if s['source_package_version'] == target]
    if not sources:
        return 'missing'
    if all(s['status'] in {'Deleted','Obsolete','Superseded'} for s in sources):
        raise RuntimeError('PPA version was already used. Preserve its upstream tarball and increment the Debian revision.')
    source = max(sources, key=lambda s:s['date_created'])
    builds = entries(source['self_link'] + '?ws.op=getBuilds')
    if any(b['buildstate'] in {'Failed to build','Dependency wait','Chroot problem','Failed to upload','Cancelled'} for b in builds):
        raise RuntimeError('Launchpad build failed. Retry that build in Launchpad; do not upload the same version again.')
    if builds and all(b['buildstate'] == 'Successfully built' for b in builds):
        query = urllib.parse.urlencode({'ws.op':'getPublishedBinaries','binary_name':PACKAGE,'exact_match':'true','version':target,'status':'Published'})
        binaries = entries(PPA + '?' + query)
        published = {b['distro_arch_series_link'] for b in binaries if b['binary_package_version'] == target}
        if all(b['distro_series_link'] + '/' + b['arch_tag'] in published for b in builds):
            return 'done'
    return 'pending'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=['copr','ppa'])
    parser.add_argument('version')
    parser.add_argument('--wait', action='store_true')
    parser.add_argument('--print-version', action='store_true')
    args = parser.parse_args()
    stable_version('v' + args.version)
    if args.print_version:
        print(ppa_version(args.version) if args.platform == 'ppa' else args.version + '-1')
        return 0
    deadline = time.monotonic() + 2700
    while True:
        result = state(args.platform, args.version)
        print(f'{args.platform} {args.version}: {result}', flush=True)
        if result == 'done': return 0
        if result == 'failed':
            if args.wait: raise RuntimeError('Remote package build failed')
            return 1
        if result == 'missing' and not args.wait: return 1
        if time.monotonic() >= deadline: raise RuntimeError('Timed out waiting for repository publication')
        time.sleep(30)


if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as error:
        print(f'::error::{error}', file=sys.stderr)
        sys.exit(2)
