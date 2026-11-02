#!/usr/bin/env python3
"""Prepare pinned upstream source and apply the maintained Android fix."""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
lock = json.loads((HERE / 'upstream.json').read_text())
destination = Path(sys.argv[1]).resolve()
if destination.exists():
    raise SystemExit('Destination must not already exist')
destination.mkdir(parents=True)
def git(*args):
    return subprocess.run(['git', '-C', str(destination), *args], check=True)
git('init', '-q')
git('remote', 'add', 'origin', 'https://github.com/getumbrel/murmur.git')
git('fetch', '--depth=1', 'origin', lock['commit'])
git('checkout', '--detach', 'FETCH_HEAD')
assert json.loads((destination / 'package.json').read_text())['version'] == lock['version']
git('apply', '--check', str(HERE / 'android-decoder.patch'))
git('apply', str(HERE / 'android-decoder.patch'))
print('Prepared Murmur', lock['version'], 'with Android decoder fallback')
