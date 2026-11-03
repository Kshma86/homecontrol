#!/usr/bin/env python3
"""Check the sealed public build artifacts before an optional image rebuild."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(kit):
    accepted = kit/'evidence/acceptance.json'
    manifest = json.loads((kit/'release.json').read_text())
    if hashlib.sha256(accepted.read_bytes()).hexdigest() != manifest['acceptance_sha256']:
        raise ValueError('Acceptance receipt changed')
    evidence = json.loads(accepted.read_text())
    receipt = kit/'evidence/build-inputs.json'
    if hashlib.sha256(receipt.read_bytes()).hexdigest() != evidence['evidence_sha256']['build-inputs.json']:
        raise ValueError('Build receipt changed')
    rows = json.loads(receipt.read_text())['sha256']
    root = kit/'build-inputs'
    for name, expected in rows.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Build input path escapes its root')
        path = root/relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Build input symlink')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Build input changed: '+name)
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if actual != set(rows):
        raise ValueError('Build inventory changed')
    print('Public build inputs verified: '+str(len(rows)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('kit', type=Path)
    verify(p.parse_args().kit.resolve())
