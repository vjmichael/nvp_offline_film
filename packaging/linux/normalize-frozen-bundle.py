#!/usr/bin/env python3
"""Stage PyInstaller regular files and internal file aliases for Debian.

The package builder continues to reject every symlink in the payload.
Only byte-identical, resolved internal regular-file aliases are materialized.
This is an offline build step on a trusted, quiescent native output tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat


def digest(path: Path) -> str:
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def normalize(source: Path, destination: Path) -> list[dict]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Source must be a real build directory')
    source = source.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Never overwrite a staged bundle')
    destination = destination.resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Bundle and staging directories must be separate')
    files = {}
    aliases = []
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source).as_posix()
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_relative_to(source) or not stat.S_ISREG(target.stat().st_mode):
                raise ValueError('Refusing external or non-file bundle alias: ' + rel)
            sha = digest(target)
            aliases.append({'path': rel, 'target': target.relative_to(source).as_posix(), 'sha256': sha})
            files[rel] = (sha, stat.S_IMODE(target.stat().st_mode))
        elif stat.S_ISREG(path.lstat().st_mode):
            files[rel] = (digest(path), stat.S_IMODE(path.lstat().st_mode))
        elif not stat.S_ISDIR(path.lstat().st_mode):
            raise ValueError('Refusing nonregular bundle object: ' + rel)
    shutil.copytree(source, destination, symlinks=False)
    result = {}
    for path in sorted(destination.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('Staged bundle contains a symlink')
        if path.is_file():
            result[path.relative_to(destination).as_posix()] = (digest(path), stat.S_IMODE(path.stat().st_mode))
        elif not path.is_dir():
            raise RuntimeError('Staged bundle contains a nonregular object')
    if result != files:
        raise RuntimeError('Bundle staging changed file bytes or modes')
    return aliases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists() or args.receipt.is_symlink():
        raise FileExistsError('Receipt already exists')
    records = normalize(args.source, args.destination)
    args.receipt.write_text(json.dumps(records, indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
