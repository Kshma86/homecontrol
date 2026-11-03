"""Prepare r21 without production mutations; reuse exactly the r20 app images."""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-containers-20261103-r23'
PRIOR = 'hc-audit-20261102-r20'
OLD = 'hc-security-20261102-r18'
KIT = BASE / 'backups/releases' / NAME


def read(path): return json.loads(path.read_text())
def write(path, value): path.write_text(json.dumps(value, indent=2) + '\n')
def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 ** 2), b''): digest.update(data)
    return digest.hexdigest()


def source():
    assert not KIT.exists()
    assert read(BASE / 'infra/access-release.json')['release'] == OLD
    prior = BASE / 'backups/releases' / PRIOR
    assert read(prior / 'deployment-status.json')['phase'] == 'previous_release_restored'
    m = read(prior / 'release.json')
    assert all(sha(prior / 'source' / n) == h for n, h in m['source_sha256'].items())
    KIT.mkdir(); (KIT / 'private').mkdir(mode=0o700); (KIT / 'evidence').mkdir(); (KIT / 'tools').mkdir()
    target = KIT / 'source'
    shutil.copytree(prior / 'source', target, ignore=shutil.ignore_patterns('__pycache__'))
    rendered = []
    for path in target.rglob('*'):
        if (path.is_file() and not path.is_relative_to(target / 'docs')
                and path.suffix in ('.py', '.sh', '.service', '.timer', '.path', '.conf', '.json')):
            text = path.read_text()
            if PRIOR in text:
                path.write_text(text.replace(PRIOR, NAME)); rendered.append(str(path.relative_to(target)))
    for name in ('router_restic.py', 'router_operation_log.py', 'tests/test_router_operation_log.py', 'tests/test_router_backup.py'):
        shutil.copyfile(BASE / 'scripts' / name, target / 'scripts' / name)
    for name in ('image_cache.py', 'test_image_cache.py', 'backup_preflight.py', 'test_backup_preflight.py', 'backup_supervision.py', 'test_backup_supervision.py'):
        text = (BASE / 'scripts/audit_release' / name).read_text().replace('homecontrol-r20-acceptance-', 'homecontrol-r21-acceptance-')
        (target / 'scripts/audit_release' / name).write_text(text)
    path = target / 'scripts/audit_release/activate.py'; text = path.read_text().replace('r20', 'r21')
    text = text.replace('def main(action=', '''def backup_checks(core, manifest):
 sys.path.insert(0,str(KIT/'source/scripts/audit_release'))
 from backup_preflight import prepare
 prepare(core,manifest)

def main(action=''')
    text = text.replace('  schedule_checks(core)\n', '  schedule_checks(core)\n  backup_checks(core,manifest)\n')
    path.write_text(text)
    path = target / 'scripts/audit_release/postcheck.py'; path.write_text(path.read_text().replace('r20', 'r21'))
    path = target / 'scripts/router_release/activate.py'; path.write_text(path.read_text().replace('router-r20', 'router-r21').replace("say('r20:", "say('r21:"))
    path = target / 'scripts/router_release/prepare_audit_restore.py'; path.write_text(path.read_text().replace('hc-audit-final-r20-', 'hc-audit-final-r21-').replace('audit-final-r20-', 'audit-final-r21-'))
    # Cache linking stays scoped to the immutable image archive; ordinary private
    # files keep independent inodes and existing permission handling.
    path = target / 'scripts/f10_release/deploy.py'; text = path.read_text()
    old = "    shutil.copyfile(KIT/'private/access-images.tar.gz',images/'access-images.tar.gz')"
    new = """    sys.path.insert(0,str(KIT/'source/scripts/audit_release'))
    from image_cache import link_archive,paths
    link_archive(paths(BASE)[0],images/'access-images.tar.gz',m['offline_image_archive_sha256'],uid=os.geteuid())"""
    assert text.count(old) == 1; text = text.replace(old, new)
    old = "    shutil.copytree(KIT/'source',RUNTIME);shutil.copytree(KIT/'private/runtime',PRIVATE);PRIVATE.chmod(0o700)"
    new = """    sys.path.insert(0,str(KIT/'source/scripts/audit_release'))
    from image_cache import link_archive
    stage=KIT/'private/runtime'
    def copy_private(source,target):
        if Path(source)==stage/'images/access-images.tar.gz':
            link_archive(source,target,m['offline_image_archive_sha256'],uid=os.geteuid())
            return str(target)
        return shutil.copy2(source,target)
    shutil.copytree(KIT/'source',RUNTIME);shutil.copytree(stage,PRIVATE,copy_function=copy_private);PRIVATE.chmod(0o700)"""
    assert text.count(old) == 1; path.write_text(text.replace(old, new))
    # These two focused fixture changes exercise the added preflight and cache
    # linking through the real activation/installation entrypoints.
    for name in ('scripts/audit_release/test_activate.py', 'scripts/f10_release/test_deploy.py'):
        shutil.copyfile(BASE / name, target / name)
    actual = json.loads(subprocess.check_output(['docker', 'inspect', *m['baseline']], text=True))
    baseline = {row['Name'].lstrip('/'): {'id': row['Id'], 'image': row['Image']} for row in actual}
    for name, before in m['baseline'].items():
        assert baseline[name]['image'] == before['image']
        if name in m['unchanged']: assert baseline[name]['id'] == before['id']
    m.update(release=NAME, baseline=baseline, source_sha256={}, acceptance_sha256=None,
             previous_compose_sha256=sha(BASE / 'infra/docker-compose.yml'), ready_for_root_deploy=False,
             deployed=False, status='preparing_pre_cutover_backup_gate', prior_attempt=PRIOR)
    write(KIT / 'release.json', m)
    os.link(prior / 'private/access-images.tar.gz', KIT / 'private/access-images.tar.gz')
    shutil.copyfile(prior / 'tools/rclone', KIT / 'tools/rclone'); (KIT / 'tools/rclone').chmod(0o755)
    for name in ('baked-code-and-packages.json', 'unchanged-regression-inputs.json'):
        shutil.copyfile(prior / 'evidence' / name, KIT / 'evidence' / ('prior-r20-' + name))
    unchanged = {}
    for prefix in ('infra/backend', 'infra/mdns', 'apps/ha-growatt-poller', 'infra/frontend', 'apps/hc_ingest', 'apps/bridge_runtime', 'apps/xiaomi-x10'):
        for path in (target / prefix).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                relative = str(path.relative_to(target)); assert sha(path) == sha(prior / 'source' / relative); unchanged[relative] = sha(path)
    write(KIT / 'evidence/unchanged-app-inputs.json', {'ok': True, 'sha256': unchanged, 'images': m['images'], 'application_code_changes': 0})
    write(KIT / 'evidence/namespace-rendering.json', {'paths': rendered, 'production_changed': False})
    print(json.dumps({'release': NAME, 'prepared': True, 'application_code_changes': 0, 'deployed': False}))


def seal():
    m = read(KIT / 'release.json')
    assert not m['ready_for_root_deploy']
    assert read(BASE / 'infra/access-release.json')['release'] == OLD
    assert read(BASE / 'backups/releases' / PRIOR / 'deployment-status.json')['phase'] == 'previous_release_restored'
    previous = read(BASE / 'backups/releases' / PRIOR / 'release.json')
    assert all(sha(BASE / 'backups/releases' / PRIOR / 'source' / n) == h for n, h in previous['source_sha256'].items())
    accepted = BASE / 'backups/releases' / PRIOR / 'evidence/acceptance.json'
    assert sha(accepted) == previous['acceptance_sha256']
    assert all(sha(accepted.parent / n) == h for n, h in read(accepted)['evidence_sha256'].items())
    old = read(BASE / 'backups/releases' / OLD / 'release.json')
    assert all(sha(BASE / 'scripts/access_runtime' / OLD / n) == h for n, h in old['source_sha256'].items())
    assert sha(BASE / 'infra/docker-compose.yml') == m['previous_compose_sha256']
    assert sha(BASE / 'HC_REFACTOR_AUDIT.md') == '51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2'
    rows = re.findall(r'^\| (HC-\d+) \|.*?\| ([^|]+) \|$', (BASE / 'AUDIT_REPAIR.md').read_text(), re.M)
    assert len(rows) == len({n for n, v in rows}) == 48
    assert sum(v.strip() == 'Ellenőrzött' for n, v in rows) == 46
    assert {n for n, v in rows if v.strip() == 'Folyamatban'} == {'HC-41', 'HC-43'}
    actual = json.loads(subprocess.check_output(['docker', 'inspect', *m['baseline']], text=True))
    for row in actual:
        name = row['Name'].lstrip('/')
        assert {'id': row['Id'], 'image': row['Image']} == m['baseline'][name]
        assert name == 'homecontrol-adminer' or row['State']['Running']
        assert row['State'].get('Health', {}).get('Status') in (None, 'healthy')
    assert sha(KIT / 'private/access-images.tar.gz') == m['offline_image_archive_sha256']
    assert sha(KIT / 'tools/rclone') == m['rclone_sha256']
    assert read(KIT / 'evidence/prior-r20-baked-code-and-packages.json')['ok']
    for n, h in read(KIT / 'evidence/unchanged-app-inputs.json')['sha256'].items():
        assert sha(KIT / 'source' / n) == h
    assert read(KIT / 'evidence/source-delta-review.json')['ok']
    tests = {'audit-final': 43, 'installer-recheck': 16, 'router': 12,
             'private-logging': 4, 'router-contracts-final': 21, 'router-workers-final': 9}
    for name, count in tests.items():
        log = (KIT / 'evidence' / (name + '-tests.log')).read_text()
        assert re.search(r'Ran ' + str(count) + r' tests in ', log), name
        assert log.rstrip().endswith('OK') and 'skipped=' not in log, name
    for path in (KIT / 'source').rglob('*'):
        assert not path.is_symlink()
        if path.is_file() and path.suffix == '.py': ast.parse(path.read_bytes(), filename=str(path))
    subprocess.run(['bash', '-n', str(KIT / 'source/scripts/bootstrap_restore_v0_1.sh')], check=True)
    m['source_sha256'] = {str(p.relative_to(KIT / 'source')): sha(p) for p in sorted((KIT / 'source').rglob('*'))
                          if p.is_file() and '__pycache__' not in p.parts}
    evidence = {str(p.relative_to(KIT / 'evidence')): sha(p) for p in sorted((KIT / 'evidence').rglob('*'))
                if p.is_file() and p.name != 'acceptance.json'}
    write(KIT / 'evidence/acceptance.json', {'ok': True, 'release': NAME,
          'state': 'sealed_ready_for_local_sudo_not_deployed', 'sealed_at': datetime.now(timezone.utc).isoformat(),
          'production_changed': False, 'prior_regression_unique_tests': 1308,
          'fresh_transaction_tests': tests, 'fresh_transaction_test_count': sum(tests.values()),
          'original_router_failure_reproduced': False, 'original_router_failure_cause': 'unknown',
          'new_full_vm_restore_performed': False, 'hc41_closed': False, 'hc43_closed': False,
          'required_root_gates': ['SHA-verified inactive image cache deduplication and free capacity',
              'full running-r18 HC/Git/router backup and archive/PG restore before cutover',
              'three-component guarded cutover', 'fresh candidate HC/Git/router and PG restore',
              'runtime hashes, unchanged components, five live timers and audit handover'],
          'evidence_sha256': evidence})
    m.update(acceptance_sha256=sha(KIT / 'evidence/acceptance.json'), ready_for_root_deploy=True,
             status='sealed_ready_for_local_sudo_not_deployed', retry_reason='full backup restore gate before cutover; private failure diagnostics and capacity preparation',
             pending_root_steps=['verify and deduplicate inactive image caches', 'full r18 HC/Git/router and PG restore before cutover',
                                 'three component cutover and IPC/health checks', 'fresh candidate HC/Git/router and PG restore',
                                 'five timers and final audit handover'])
    write(KIT / 'release.json', m)
    print(json.dumps({'release': NAME, 'ready_for_root_deploy': True, 'source_files': len(m['source_sha256']),
                      'fresh_tests': sum(tests.values()), 'deployed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('source', 'seal'))
    args = parser.parse_args(); globals()[args.action]()
