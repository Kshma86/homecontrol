"""Prepare r20 from sealed r19; reuse verified app images, fix schedule acceptance."""
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
OLD = 'hc-security-20261102-r18'
PRIOR = 'hc-audit-20261102-r19'
NAME = 'hc-audit-20261102-r20'
KIT = BASE / 'backups/releases' / NAME
PREVIOUS = BASE / 'backups/releases' / PRIOR
PATCHES = ('activate.py', 'postcheck.py', 'schedules.py', 'test_activate.py', 'test_postcheck.py', 'test_schedules.py')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(part)
    return h.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def check_prior():
    old = read(PREVIOUS / 'release.json')
    assert all(digest(PREVIOUS / 'source' / n) == h for n, h in old['source_sha256'].items())
    acceptance = PREVIOUS / 'evidence/acceptance.json'
    assert digest(acceptance) == old['acceptance_sha256']
    assert all(digest(PREVIOUS / 'evidence' / n) == h for n, h in read(acceptance)['evidence_sha256'].items())
    assert read(PREVIOUS / 'deployment-status.json')['phase'] == 'previous_release_restored'
    assert read(BASE / 'infra/access-release.json')['release'] == OLD
    return old


def source():
    assert not KIT.exists(), 'Never overwrite a release'
    old = check_prior()
    KIT.mkdir()
    (KIT / 'private').mkdir(mode=0o700)
    (KIT / 'evidence').mkdir()
    (KIT / 'tools').mkdir()
    target = KIT / 'source'
    shutil.copytree(PREVIOUS / 'source', target, ignore=shutil.ignore_patterns('__pycache__'))
    rendered = []
    for path in target.rglob('*'):
        if not path.is_file() or path.is_relative_to(target / 'docs'):
            continue
        if path.suffix in ('.py', '.sh', '.service', '.timer', '.path', '.conf', '.json'):
            text = path.read_text()
            if PRIOR in text:
                path.write_text(text.replace(PRIOR, NAME))
                rendered.append(str(path.relative_to(target)))
    for name in PATCHES:
        text = (BASE / 'scripts/audit_release' / name).read_text()
        text = text.replace(PRIOR, NAME)
        if name in ('activate.py', 'postcheck.py'):
            text = text.replace('r19', 'r20')
        (target / 'scripts/audit_release' / name).write_text(text)
    # Retain historical documents and the original r19 builder as evidence.
    # Only the operational exporter/probe/runner receives the new namespace.
    router = target / 'scripts/router_release/activate.py'
    router.write_text(router.read_text().replace('router-r19', 'router-r20').replace("say('r19:", "say('r20:"))
    export = target / 'scripts/router_release/prepare_audit_restore.py'
    export.write_text(export.read_text().replace('hc-audit-final-r19-', 'hc-audit-final-r20-').replace('audit-final-r19-', 'audit-final-r20-'))
    process = target / 'scripts/audit_release/run_process_lab.py'
    process.write_text(process.read_text().replace('hc-r19-process-fixture', 'hc-r20-process-fixture'))
    model = read(target / 'runtime.compose.json')
    write(target / 'runtime.compose.json', model)
    names = list(old['baseline'])
    actual = json.loads(subprocess.check_output(['docker', 'inspect', *names], text=True))
    baseline = {r['Name'].lstrip('/'): {'id': r['Id'], 'image': r['Image']} for r in actual}
    for n, before in old['baseline'].items():
        assert baseline[n]['image'] == before['image'], n
        if n in old['unchanged']:
            assert baseline[n]['id'] == before['id'], n
    m = copy.deepcopy(old)
    m.update(release=NAME, baseline=baseline, source_sha256={}, acceptance_sha256=None,
             previous_compose_sha256=digest(BASE / 'infra/docker-compose.yml'),
             ready_for_root_deploy=False, deployed=False, status='retry_preparing_not_deployed',
             prior_attempt=PRIOR, retry_reason='stale F6 installed enabled flags rejected five actually active timers')
    write(KIT / 'release.json', m)
    shutil.copyfile(PREVIOUS / 'tools/rclone', KIT / 'tools/rclone')
    (KIT / 'tools/rclone').chmod(0o755)
    # A hard link avoids a redundant 2 GB archive; both copies stay immutable.
    assert digest(PREVIOUS / 'private/access-images.tar.gz') == m['offline_image_archive_sha256']
    os.link(PREVIOUS / 'private/access-images.tar.gz', KIT / 'private/access-images.tar.gz')
    inherited = KIT / 'evidence/prior-r19'
    inherited.mkdir()
    shutil.copyfile(PREVIOUS / 'release.json', inherited / 'release.json')
    shutil.copyfile(PREVIOUS / 'evidence/acceptance.json', inherited / 'acceptance.json')
    for n in read(PREVIOUS / 'evidence/acceptance.json')['evidence_sha256']:
        dest = inherited / 'evidence' / n
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PREVIOUS / 'evidence' / n, dest)
    for n in ('deployment-status.json', 'evidence/router-live-acceptance.json'):
        dest = inherited / n
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PREVIOUS / n, dest)
    # Exact unchanged app/test inputs justify retaining the original regression.
    same = {}
    for prefix in ('infra/backend', 'infra/mdns', 'apps/ha-growatt-poller', 'infra/frontend',
                   'apps/bridge_runtime', 'apps/hc_ingest', 'apps/xiaomi-x10'):
        for path in (target / prefix).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                n = str(path.relative_to(target))
                assert digest(path) == digest(PREVIOUS / 'source' / n), n
                same[n] = digest(path)
    write(KIT / 'evidence/unchanged-regression-inputs.json', {
        'ok': True, 'prior_release': PRIOR, 'unchanged_files': same,
        'prior_unique_regression_tests': 1308, 'new_app_images_built': 0,
        'application_changes_since_r19': 0, 'rendered_operational_paths': rendered,
        'patched_activation_files': list(PATCHES), 'production_changed': False})
    write(KIT / 'evidence/candidate-image-lock.json', read(PREVIOUS / 'evidence/candidate-image-lock.json'))
    print(json.dumps({'release': NAME, 'prepared': True, 'reused_images': 3,
                      'identical_app_and_test_files': len(same), 'production_changed': False}))


def seal():
    check_prior()
    m = read(KIT / 'release.json')
    assert not m['ready_for_root_deploy']
    assert digest(BASE / 'HC_REFACTOR_AUDIT.md') == '51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2'
    rows = re.findall(r'^\| (HC-\d+) \|.*?\| ([^|]+) \|$', (BASE / 'AUDIT_REPAIR.md').read_text(), re.M)
    assert len(rows) == 48 and len({n for n, v in rows}) == 48
    assert sum(v.strip() == 'Ellenőrzött' for n, v in rows) == 46
    assert {n for n, v in rows if v.strip() == 'Folyamatban'} == {'HC-41', 'HC-43'}
    assert digest(BASE / 'infra/docker-compose.yml') == m['previous_compose_sha256']
    for name, before in m['baseline'].items():
        row = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
        assert {'id': row['Id'], 'image': row['Image']} == before
        assert name == 'homecontrol-adminer' or row['State']['Running']
        assert row['State'].get('Health', {}).get('Status') in (None, 'healthy')
    for n, h in read(KIT / 'evidence/unchanged-regression-inputs.json')['unchanged_files'].items():
        assert digest(KIT / 'source' / n) == h
    assert read(KIT / 'evidence/baked-code-and-packages.json')['ok']
    counts = {}
    for label, count in (('installer', 16), ('router', 12), ('audit-retry', 26)):
        log = (KIT / 'evidence' / (label + '-tests.log')).read_text()
        assert re.search(r'Ran ' + str(count) + r' tests in ', log) and log.rstrip().endswith('OK'), label
        counts[label] = count
    for path in (KIT / 'source').rglob('*'):
        assert not path.is_symlink()
        if path.is_file() and path.suffix == '.py':
            ast.parse(path.read_bytes(), filename=str(path))
    subprocess.run(['bash', '-n', str(KIT / 'source/scripts/bootstrap_restore_v0_1.sh')], check=True)
    assert digest(KIT / 'private/access-images.tar.gz') == m['offline_image_archive_sha256']
    assert digest(KIT / 'tools/rclone') == m['rclone_sha256']
    assert read(KIT / 'evidence/generated-schedule-fixture.json')['ok']
    schedules = read(KIT / 'evidence/readonly-live-schedules.json')
    assert schedules['ok'] and len(schedules['timers']) == 5
    assert not (BASE / 'docs/audit-final-20261102.md').exists()
    m['source_sha256'] = {str(p.relative_to(KIT / 'source')): digest(p)
                          for p in sorted((KIT / 'source').rglob('*'))
                          if p.is_file() and '__pycache__' not in p.parts}
    receipt = {'ok': True, 'release': NAME, 'sealed_at': datetime.now(timezone.utc).isoformat(),
               'state': 'sealed_retry_ready_for_local_sudo_not_deployed', 'production_changed': False,
               'prior_regression_unique_tests': 1308, 'fresh_transaction_tests': counts,
               'reused_exact_image_ids': m['images'], 'hc41_closed': False, 'hc43_closed': False,
               'fresh_r20_vm_restore_performed': False,
               'evidence_sha256': {str(p.relative_to(KIT / 'evidence')): digest(p)
                                  for p in sorted((KIT / 'evidence').rglob('*')) if p.is_file()}}
    write(KIT / 'evidence/acceptance.json', receipt)
    m.update(acceptance_sha256=digest(KIT / 'evidence/acceptance.json'), ready_for_root_deploy=True,
             status='sealed_retry_ready_for_local_sudo_not_deployed')
    write(KIT / 'release.json', m)
    print(json.dumps({'release': NAME, 'ready_for_root_deploy': True,
                      'source_files': len(m['source_sha256']), 'deployed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('source', 'seal'))
    args = parser.parse_args()
    globals()[args.action]()
