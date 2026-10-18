#!/usr/bin/env python3
"""Lint community apps with the official catalog available for dependencies/ports.

Usage: python tests/lint_store.py /path/to/pinned/umbrel-apps
The upstream checkout must have its npm dependencies installed.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    upstream = Path(sys.argv[1]).resolve()
    apps = sorted(path for path in ROOT.iterdir() if (path / 'umbrel-app.yml').is_file())
    with tempfile.TemporaryDirectory(prefix='umbrel-store-lint-') as tmp:
        catalog = Path(tmp)
        for path in upstream.iterdir():
            if (path / 'umbrel-app.yml').is_file():
                shutil.copytree(path, catalog / path.name)
        for path in apps:
            if (catalog / path.name).exists():
                raise ValueError(f'Community app shadows official app: {path.name}')
            shutil.copytree(path, catalog / path.name)
        return subprocess.run([
            'node', str(upstream / '.tools/lint-apps.mjs'), '--root', str(catalog),
            *[path.name for path in apps], '--check-images',
        ]).returncode


if __name__ == '__main__':
    sys.exit(main())
