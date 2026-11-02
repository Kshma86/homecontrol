#!/usr/bin/env python3
"""Check the delegated external Git copy; print counts and paths, never values."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

BASE = Path('/srv/docker/homecontrol')
REPO = Path('/tmp/hc-router-audit-20261101/input/git.git')
sys.path.insert(0, str(BASE / 'infra/backend'))
from backup_export import check_public_file


def git(*args):
    return subprocess.check_output(['git', '--git-dir', str(REPO), *args])


receipt = json.loads((REPO.parent / 'input.json').read_text())
head = git('rev-parse', 'refs/heads/main').decode().strip()
assert head == receipt['git_commit']
manifest = json.loads(git('show', head + ':EXPORT_MANIFEST.json'))
head_paths = git('ls-tree', '-r', '--name-only', head).decode().splitlines()
present = set(head_paths)
bad_hashes = []
missing_paths = []
for row in manifest['files']:
    if row['path'] not in present:
        missing_paths.append(row['path'])
        continue
    if hashlib.sha256(git('show', head + ':' + row['path'])).hexdigest() != row['sha256']:
        bad_hashes.append(row['path'])
objects = git('rev-list', '--objects', '--all').decode().splitlines()
names = {line.partition(' ')[0]: line.partition(' ')[2] for line in objects}
metadata = git('cat-file', '--batch-all-objects', '--batch-check=%(objectname) %(objecttype) %(objectsize)').decode().splitlines()
findings = []
checked = 0
with tempfile.TemporaryDirectory(prefix='hc-git-scan-') as temporary:
    for row in metadata:
        object_id, kind, size = row.split()
        if kind != 'blob':
            continue
        name = names.get(object_id, '')
        path = Path(temporary) / ('blob.json' if name.lower().endswith('.json') else 'blob')
        path.write_bytes(git('cat-file', 'blob', object_id))
        path.chmod(0o600)
        try:
            check_public_file(path)
        except ValueError:
            findings.append({'object': object_id, 'path': name, 'reason': 'private_key_or_credential_field'})
        checked += 1
        path.unlink()
private_paths = [name for name in head_paths if re.search(
    r'(^|/)(?:\.env(?:\..*)?|.*-key\.txt|xiaomi_cloud_auth.*|multi_connector_config\.json.*)$|^infra/ssh/', name)]
report = {'ok': not bad_hashes and not findings and not private_paths and not missing_paths,
          'git_commit': head, 'commits': int(git('rev-list', '--count', '--all')),
          'historical_blobs_scanned': checked, 'manifest_files_verified': len(manifest['files']),
          'manifest_hash_mismatches': bad_hashes, 'credential_findings': findings,
          'manifest_missing_paths': missing_paths,
          'private_paths_in_head': private_paths, 'remote_write_commands': 0,
          'scan_scope': 'private-key headers and non-placeholder sensitive fields in JSON, same policy as public export'}
(Path(__file__).parent / 'git-verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(0 if report['ok'] else 1)
