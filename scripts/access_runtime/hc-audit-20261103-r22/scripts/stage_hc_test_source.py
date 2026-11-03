"""Stage explicit public inputs and test-only policy variants under /tmp."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ('infra/backend', 'infra/mdns', 'apps/bridge_runtime', 'apps/tuya-poller',
           'apps/gree-climate', 'apps/xiaomi-x10', 'apps/hc_ingest',
           'apps/ha-growatt-poller', 'apps/ai-server')


def stage(output, profile='deployed'):
    output = Path(output)
    if output.parent.resolve() != Path('/tmp') or output.exists() or output.is_symlink():
        raise ValueError('Use a new directory directly under /tmp')
    if profile not in ('deployed', 'standard'):
        raise ValueError('Unknown test policy')
    marker = json.loads((ROOT/'infra/access-release.json').read_text())
    source = ROOT/'scripts/access_runtime'/marker['release']
    shutil.copytree(source, output, ignore=shutil.ignore_patterns('__pycache__'))
    for folder in FOLDERS:
        target = output/folder
        target.mkdir(parents=True, exist_ok=True)
        # A source overlay must also honor deletions. Otherwise a removed
        # repository module/test silently survives from the deployed baseline.
        for path in target.glob('*.py'):
            if not (ROOT/folder/path.name).is_file():
                path.unlink()
        for path in (ROOT/folder).glob('*.py'):
            shutil.copyfile(path, target/path.name)
        tests = ROOT/folder/'tests'
        if tests.exists():
            for path in (target/'tests').glob('*.py'):
                if not (tests/path.name).is_file():
                    path.unlink()
            shutil.copytree(tests, target/'tests', dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__'))
    for path in (ROOT/'scripts').glob('*.py'):
        shutil.copyfile(path, output/'scripts'/path.name)
    shutil.copyfile(ROOT/'scripts/access_release/restore_assets.py',
                    output/'scripts/access_release/restore_assets.py')
    if (ROOT/'scripts/security_release').exists():
        shutil.copytree(ROOT/'scripts/security_release', output/'scripts/security_release',
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    # Tests validate the vendored reference against this reviewed public handoff.
    handoff = ROOT/'hc-v31-qspi-handoff-20261009-rcp1-foundation.zip'
    shutil.copyfile(handoff, output/handoff.name)
    shutil.copytree(ROOT/'infra/frontend', output/'infra/frontend', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('node_modules', 'dist', '__pycache__'))
    changes = []
    if profile == 'standard':
        # Generic legacy contracts use fake external commands and synthetic data.
        # Only this disposable source copy gets the optional development policy;
        # the deployed profile separately checks the exact mandatory policy.
        policy = output/'infra/backend/deployment_policy.py'
        text = policy.read_text()
        if 'POLICY_REQUIRED = True' not in text:
            raise ValueError('Expected mandatory deployment policy')
        policy.write_text(text.replace('POLICY_REQUIRED = True', 'POLICY_REQUIRED = False', 1))
        (output/'infra/backend/deployment_policy.json').unlink(missing_ok=True)
        changes = ['optional policy in disposable standard-profile source only']
    report = {'release': marker['release'], 'policy_profile': profile,
              'test_only_changes': changes, 'production_changed': False,
              'source_sha256': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in output.rglob('*') if p.is_file()}}
    (output/'.hc-test-source.json').write_text(json.dumps(report, indent=2)+'\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--policy', choices=('deployed', 'standard'), default='deployed')
    args = parser.parse_args()
    print(stage(args.output, args.policy))
