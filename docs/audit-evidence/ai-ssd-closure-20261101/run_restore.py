#!/usr/bin/env python3
"""Run the real canonical restore only inside the guarded disposable guest."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from setup_guest import guard

guard()
os.umask(0o077)
mode = sys.argv[1]
assert mode in ('fresh', 'repeat', 'unavailable')
base = Path('/srv/docker/homecontrol')
if mode == 'fresh':
    assert not base.exists()
elif mode == 'repeat':
    assert json.loads(Path('/lab/fresh.json').read_text())['ok']
else:
    assert base.is_dir()
receipt = json.loads(Path('/lab/input/input.json').read_text())
candidate = Path('/lab/candidate.json')
selected = json.loads(candidate.read_text()) if candidate.exists() else {'git_commit': receipt['git_commit']}
args = ['bash', '/lab/candidate-project/scripts/bootstrap_restore_v0_1.sh' if candidate.exists() else '/lab/seed-project/scripts/bootstrap_restore_v0_1.sh',
        '--age-key', '/lab/input/age-key.txt', '--repo-url', '/lab/candidate.git' if candidate.exists() else '/lab/input/git.git',
        '--repo-ref', selected['git_commit'], '--router-settings', '/lab/input/router-settings.json',
        '--snapshot', receipt['snapshot_id'], '--work-dir', '/lab/' + ('unavailable' if mode == 'unavailable' else 'restore'),
        '--apply', '--apply-restic-files', '--restore-db', '--confirm-db-replace', '--start']
report = {'mode': mode, 'snapshot_id': receipt['snapshot_id'], 'git_commit': selected['git_commit'],
          'external_git_commit': receipt['git_commit'], 'candidate_fixes_applied': candidate.exists(),
          'started_at': datetime.now(timezone.utc).isoformat(), 'ok': False}
with Path('/lab/' + mode + '.log').open('x') as log:
    result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, timeout=10800)
report.update(returncode=result.returncode, ok=result.returncode == 0,
              finished_at=datetime.now(timezone.utc).isoformat())
Path('/lab/' + mode + '.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(result.returncode)
