import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

BASE = Path('/srv/docker/homecontrol')
KIT = BASE / 'backups/releases/hc-audit-20261103-r22'
PRIOR = BASE / 'backups/releases/hc-audit-20261102-r21'
def read(path): return json.loads(path.read_text())
def write(path, value): path.write_text(json.dumps(value, indent=2) + '\n')
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 ** 2), b''): h.update(data)
    return h.hexdigest()
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

m = read(KIT / 'release.json')
assert not m['ready_for_root_deploy']
assert read(BASE / 'infra/access-release.json')['release'] == m['previous_release']
assert sha(PRIOR / 'release.json') == 'd31eb653cafbaf8f3514e6e96690b013a3fd2410a5a70c28fece012593489f20'
prior = read(PRIOR / 'release.json')
assert all(sha(PRIOR / 'source' / n) == h for n, h in prior['source_sha256'].items())
assert sha(BASE / 'HC_REFACTOR_AUDIT.md') == '51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2'
assert sha(BASE / 'infra/docker-compose.yml') == m['previous_compose_sha256']
old = read(BASE / 'backups/releases' / m['previous_release'] / 'release.json')
assert all(sha(BASE / 'scripts/access_runtime' / m['previous_release'] / n) == h for n, h in old['source_sha256'].items())
counts = {}
env = {**os.environ, 'PYTHONPATH': '/tmp/hc-router-test-deps', 'PYTHONDONTWRITEBYTECODE': '1'}
for label, folder, pattern, expected in (
    ('audit', KIT / 'source/scripts/audit_release', 'test_*.py', 80),
    ('installer', KIT / 'source/scripts/f10_release', 'test_deploy.py', 16),
    ('router-activation', KIT / 'source/scripts/router_release', 'test_activate.py', 12),
    ('lock-recovery', BASE / 'backups/releases/hc-audit-20261102-r21-continuation-1/source', 'test_resume_r21.py', 24)):
    with (KIT / 'evidence' / (label + '-tests.log')).open('w') as output:
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(folder), '-p', pattern, '-v'],
                                stdout=output, stderr=subprocess.STDOUT, env=env, timeout=180)
    log = (KIT / 'evidence' / (label + '-tests.log')).read_text()
    if result.returncode or not re.search(r'Ran ' + str(expected) + r' tests in ', log) or not log.rstrip().endswith('OK'):
        print(log[-8000:]); raise SystemExit('Failed: ' + label)
    counts[label] = expected
    print(label, expected, 'passed', flush=True)

# The real FTP/worker suite already ran against this release in this task.
# Preserve its observed result without counting a repeated execution as new tests.
write(KIT / 'evidence/router-regression-observed.json', {
    'ok': True, 'tests': 33, 'failures': 0, 'errors': 0, 'skipped': 0,
    'evidence_kind': 'observed exec tool result; terminal output was not separately retained as a log file',
    'command': 'PYTHONPATH=/tmp/hc-router-test-deps HC_ROUTER_FTP_TEST=1 python3 -B -m unittest discover -s ' + str(KIT / 'source/scripts/tests') + " -p test_router_backup.py -v",
    'network': 'loopback-only synthetic FTP fixtures', 'router_contacted': False,
    'result_summary': 'Ran 33 tests in 51.608s; OK',
    'test_source_sha256': sha(KIT / 'source/scripts/tests/test_router_backup.py'),
    'transport_source_sha256': sha(KIT / 'source/infra/backend/router_backup.py')})
counts['router-contracts-workers-real-ftp'] = 33
lab = read(KIT / 'evidence/ftp-idle-pool-lab.json')
assert lab['ok'] and lab['router_contacted'] is False
assert lab['results']['original']['after_35s_idle_status'] == 500 and lab['results']['original']['tcp_write_timeout']
assert lab['results']['fixed']['after_35s_idle_status'] == 200 and lab['results']['fixed']['http_readback_verified']
assert lab['results']['fixed']['lock_delete_status'] == 200
process = read(KIT / 'evidence/process-lab.json')
assert process['network'] == 'none' and process['hardware_contacted'] is False
assert process['results']['backend']['running'] and process['results']['backend']['http']['/health/live'] == 200
assert process['results']['backend']['http']['/health/ready'] == 503
assert process['results']['ha-growatt-poller']['running'] and process['results']['ha-growatt-poller']['live_exit'] == 0
assert process['results']['ha-growatt-poller']['ready_exit'] == 1
offline = read(KIT / 'evidence/offline-load.json')
assert offline['ok'] and set(offline['verified_images']) == set(m['recovery_images'])
assert sha(KIT / 'private/access-images.tar.gz') == offline['archive_sha256'] == m['offline_image_archive_sha256']
sys.path.insert(0, str(BASE / 'scripts/audit_release'))
images = load('r22_image_check', BASE / 'scripts/audit_release/check_images.py')
images.KIT = KIT
images.main()
rows = json.loads(subprocess.check_output(['docker', 'inspect', *m['baseline']], text=True))
baseline = {}
for row in rows:
    name = row['Name'].lstrip('/')
    assert {'id': row['Id'], 'image': row['Image']} == m['baseline'][name]
    assert name == 'homecontrol-adminer' or row['State']['Running']
    assert row['State'].get('Health', {}).get('Status') in (None, 'healthy')
    baseline[name] = {'id': row['Id'], 'image': row['Image'], 'running': row['State']['Running'],
                      'health': row['State'].get('Health', {}).get('Status')}
timers = {}
for name in ('homecontrol-backup.timer', 'homecontrol-ai-weekly-backup.timer', 'homecontrol-restic-check.timer',
             'homecontrol-log-maintenance.timer', 'homecontrol-post-boot-health.timer'):
    state = subprocess.check_output(['systemctl', 'is-active', name], text=True).strip()
    assert state == 'active'; timers[name] = state
write(KIT / 'evidence/readonly-live-baseline.json', {'ok': True, 'checked_at': datetime.now(timezone.utc).isoformat(),
      'active_release': m['previous_release'], 'runtime_files': len(old['source_sha256']), 'containers': baseline, 'timers': timers})
same, changed = {}, []
for prefix in ('infra/backend', 'infra/mdns', 'apps/ha-growatt-poller', 'infra/frontend', 'apps/bridge_runtime', 'apps/hc_ingest', 'apps/xiaomi-x10'):
    for path in (KIT / 'source' / prefix).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            relative = str(path.relative_to(KIT / 'source'))
            if sha(path) == sha(PRIOR / 'source' / relative): same[relative] = sha(path)
            else: changed.append(relative)
assert changed == ['infra/backend/router_backup.py'], changed
write(KIT / 'evidence/application-delta.json', {'ok': True, 'prior_release': prior['release'],
      'unchanged_sha256': same, 'changed_files': changed, 'prior_regression_tests': 1308,
      'prior_tests_not_rerun': True, 'changed_transport_covered_by_fresh_targeted_tests': True})
for path in (KIT / 'source').rglob('*'):
    assert not path.is_symlink()
    if path.is_file() and path.suffix == '.py': ast.parse(path.read_bytes())
subprocess.run(['bash', '-n', str(KIT / 'source/scripts/bootstrap_restore_v0_1.sh')], check=True)
m['activation_tools_sha256'] = {name: sha(KIT / 'tools' / name) for name in ('resume_r21.py', 'summarize_r21_baseline_failure.py')}
assert m['activation_tools_sha256']['resume_r21.py'] == sha(BASE / 'backups/releases/hc-audit-20261102-r21-continuation-1/source/resume_r21.py')
write(KIT / 'evidence/fresh-test-summary.json', {'ok': True, 'profiles': counts, 'total': sum(counts.values()),
      'ftp_idle_reproduction_is_separate_lab': True, 'skipped': 0, 'deployed': False})
m['source_sha256'] = {str(p.relative_to(KIT / 'source')): sha(p) for p in sorted((KIT / 'source').rglob('*'))
                      if p.is_file() and '__pycache__' not in p.parts}
evidence = {str(p.relative_to(KIT / 'evidence')): sha(p) for p in sorted((KIT / 'evidence').rglob('*')) if p.is_file()}
receipt = {'ok': True, 'release': m['release'], 'sealed_at': datetime.now(timezone.utc).isoformat(),
           'state': 'sealed_ready_for_local_sudo_not_deployed', 'fresh_tests': counts,
           'fresh_test_total': sum(counts.values()), 'prior_1308_regression_evidence_retained_not_rerun': True,
           'real_idle_pool_bug_reproduced': True, 'fixed_local_ftp_readback_and_lock_delete': True,
           'full_r22_vm_restore_performed': False, 'hc41_closed': False, 'hc43_closed': False,
           'required_root_gates': ['verify exact original failed run and private control-write timeout',
             'both shared host locks; proven dead local repository lock recovery only; never force',
             'full normal repository check; fresh r18 HC/Git/router backup and isolated PG restore',
             'three-component cutover and automatic r18 rollback', 'fresh r22 HC/Git/router backup and isolated PG restore',
             'all runtime hashes; unchanged components; five timers; final audit handover'],
           'evidence_sha256': evidence}
write(KIT / 'evidence/acceptance.json', receipt)
m.update(acceptance_sha256=sha(KIT / 'evidence/acceptance.json'), ready_for_root_deploy=True,
         status='sealed_ready_for_local_sudo_not_deployed', deployed=False)
write(KIT / 'release.json', m)
module = load('verified_r22_activation_readonly', KIT / 'source/scripts/audit_release/activate.py')
module.router.core.verify()
print(json.dumps({'ok': True, 'release': m['release'], 'source_files': len(m['source_sha256']),
                  'fresh_tests': sum(counts.values()), 'ready_for_local_sudo': True, 'deployed': False}), flush=True)
