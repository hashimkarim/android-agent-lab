#!/usr/bin/env python3
"""Compare remote recipe metadata without executing a PKGBUILD or formula."""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from prepare_distribution import stable_version


def compare(path, platform, target):
    stable_version('v' + target)
    if not path.exists():
        return 'missing'
    patterns = {'aur': r'^pkgver=(\d+\.\d+\.\d+)\s*$',
                'homebrew': r'^  version "(\d+\.\d+\.\d+)"$'}
    matches = re.findall(patterns[platform], path.read_text(), re.M)
    if len(matches) != 1:
        raise ValueError('Cannot determine published version; refusing to guess')
    current = tuple(map(int, matches[0].split('.')))
    wanted = tuple(map(int, target.split('.')))
    if current > wanted:
        raise ValueError('Package repository already has a newer version; refusing a downgrade')
    return 'done' if current == wanted else 'older'


if __name__ == '__main__':
    try:
        result = compare(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
        print(f'{sys.argv[2]} recipe: {result}')
        sys.exit(10 if result == 'done' else 0)
    except (ValueError, OSError) as error:
        print(f'::error::{error}', file=sys.stderr)
        sys.exit(1)
