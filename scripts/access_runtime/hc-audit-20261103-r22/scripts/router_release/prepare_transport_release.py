#!/usr/bin/env python3
"""Build r15 from sealed r14 and the verified, narrowly scoped FTP transport fix."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

BASE = Path('/srv/docker/homecontrol')
OLD = 'hc-router-backup-20261101-r14'
NAME = 'hc-audit-20261103-r22'
KIT = BASE / 'backups/releases' / NAME


def source():
    if KIT.exists():
        raise ValueError('Release exists; never overwrite a sealed or partially deployed kit')
    if json.loads((BASE / 'infra/access-release.json').read_text())['release'] != OLD:
        raise ValueError('Active baseline changed')
    prior = BASE / 'backups/releases' / OLD
    manifest = json.loads((prior / 'release.json').read_text())
    proofs = []
    for path in sorted((prior / 'evidence').glob('router-transport-2*.json')):
        value = json.loads(path.read_text())
        if (value.get('ok') and value.get('serialized_verified')
                and value.get('serialized', {}).get('check') == 'full_data_verified'
                and value.get('archive_restore') == 'sha256_verified'
                and value.get('database') == 'isolated_restore_verified'):
            proofs.append(path)
    if not proofs:
        raise ValueError('No successful live transport, archive and database proof')
    for name, expected in manifest['source_sha256'].items():
        if builder.digest(prior / 'source' / name) != expected:
            raise ValueError('Sealed baseline source changed: ' + name)
    rows = json.loads(subprocess.check_output(['docker', 'inspect', *manifest['baseline']]))
    KIT.mkdir()
    for name in ('private', 'evidence', 'tools'):
        (KIT / name).mkdir(mode=0o700 if name == 'private' else 0o755)
    target = KIT / 'source'
    shutil.copytree(prior / 'source', target, ignore=shutil.ignore_patterns('__pycache__'))
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.sh', '.service', '.timer', '.path', '.conf', '.json'):
            text = path.read_text()
            if OLD in text:
                path.write_text(text.replace(OLD, NAME))
    for name in ('infra/backend/router_backup.py', 'scripts/tests/test_router_backup.py',
                 'scripts/router_release/resume_policy.py', 'scripts/router_release/test_resume_policy.py',
                 'scripts/router_release/prepare.py', 'scripts/router_release/prepare_transport_release.py'):
        shutil.copyfile(BASE / name, target / name)
    shutil.copyfile(BASE / 'scripts/router_release/activate_transport.py', target / 'scripts/router_release/activate.py')
    deploy = target / 'scripts/f10_release/deploy.py'
    deploy.write_text(builder.replace_once(deploy.read_text(),
        "OLD='hc-f10-20261031-r13'", 'OLD=' + repr(OLD)))
    tests = target / 'scripts/router_release/test_activate.py'
    text = tests.read_text()
    setup = """        self.settings.update(restic_enabled=False, ai_weekly_backup_enabled=False)
        (self.base / 'backups/backup_settings.json').write_text(json.dumps(self.settings))
        (self.kit / 'evidence').mkdir()
        (self.kit / 'evidence/incident-containment.json').write_text(json.dumps({
            'before': {'restic_enabled': True, 'ai_weekly_backup_enabled': True},
            'after': {'restic_enabled': False, 'ai_weekly_backup_enabled': False}}))

"""
    text = builder.replace_once(text, '    def test_requires_real_sudo_before_any_operation(self):',
                               setup + '    def test_requires_real_sudo_before_any_operation(self):')
    text = builder.replace_once(text, "patch.object(activate, 'candidate_settings', return_value={}),",
                               "patch.object(activate, 'candidate_settings', return_value={}), patch.object(activate, 'RouterRepository'),")
    tests.write_text(text)
    model = json.loads((BASE / 'infra/docker-compose.yml').read_text())
    for name in ('backend', 'frontend'):
        service = model['services'][name]
        for entry in service.get('env_file', []):
            entry['path'] = entry['path'].replace('/' + OLD + '/', '/' + NAME + '/')
        for entry in service.get('volumes', []):
            entry['source'] = entry['source'].replace('/' + OLD + '/', '/' + NAME + '/')
    (target / 'runtime.compose.json').write_text(json.dumps(model, indent=2) + '\n')
    manifest.update(release=NAME, previous_release=OLD, changed_services=['backend', 'frontend'],
        previous_compose_sha256=builder.digest(BASE / 'infra/docker-compose.yml'),
        baseline={row['Name'].lstrip('/'): {'id': row['Id'], 'image': row['Image']} for row in rows},
        source_sha256={}, acceptance_sha256=None, ready_for_root_deploy=False, deployed=False,
        scope=['Verified serialized FTP transport, full data checks around retention; restore incident-suspended weekly schedule'],
        status='preparing_router_transport_fix', live_transport_proof='live-transport-proof.json',
        baseline_transport_proof=proofs[-1].name)
    (KIT / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(prior / 'tools/rclone', KIT / 'tools/rclone')
    (KIT / 'tools/rclone').chmod(0o755)
    shutil.copyfile(proofs[-1], KIT / 'evidence/live-transport-proof.json')
    shutil.copyfile(prior / 'evidence/router-incident-containment.json', KIT / 'evidence/incident-containment.json')


spec = importlib.util.spec_from_file_location('router_builder', Path(__file__).with_name('prepare.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
builder.OLD, builder.NAME, builder.KIT = OLD, NAME, KIT

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('source', 'build', 'seal'))
    args = parser.parse_args()
    {'source': source, 'build': builder.build, 'seal': builder.seal}[args.action]()
