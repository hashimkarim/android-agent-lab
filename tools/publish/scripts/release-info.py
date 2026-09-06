#!/usr/bin/env python3
"""Require the latest published stable release before preparing or publishing packages."""
import json
import os
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from prepare_distribution import stable_version

REPOSITORY = 'Hashim-K/android-agent-lab'


def get(path):
    headers = {'Cache-Control': 'no-cache', 'Accept': 'application/vnd.github+json',
               'User-Agent': 'android-agent-lab-publishing'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    request = urllib.request.Request(f'https://api.github.com/repos/{REPOSITORY}/' + path, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def validate(tag):
    version = stable_version(tag)
    release = get('releases/tags/' + tag)
    if release['tag_name'] != tag or release['draft'] or release['prerelease']:
        raise ValueError('Only published stable releases can enter package repositories')
    latest = get('releases/latest')['tag_name']
    if latest != tag:
        raise ValueError(f'Refusing {tag}: latest stable release is {latest}')
    assets = {a['name'] for a in release['assets']}
    required = {'SHA256SUMS', *(f'Android-Agent-Lab-{version}-{a}.tar.gz' for a in ('x64', 'arm64'))}
    if not required <= assets:
        raise ValueError('Release is missing architecture bundles or SHA256SUMS')
    return version


if __name__ == '__main__':
    try:
        print(validate(sys.argv[1]))
    except Exception as error:
        print(f'::error::{error}', file=sys.stderr)
        sys.exit(1)
