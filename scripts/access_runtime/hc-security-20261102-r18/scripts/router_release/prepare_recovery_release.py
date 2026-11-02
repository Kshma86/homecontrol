#!/usr/bin/env python3
"""Prepare r16 recovery/export corrections from the unchanged, sealed live r15."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

BASE = Path('/srv/docker/homecontrol')
OLD = 'hc-router-backup-20261101-r15'
NAME = 'hc-security-20261102-r18'
KIT = BASE / 'backups/releases' / NAME
FILES = (
    'infra/backend/backup_export.py', 'infra/backend/backup_export_manifest.py',
    'scripts/export_config_snapshot.py', 'scripts/backup_offsite_worker.sh',
    'scripts/backup_config_sync_worker.sh', 'scripts/access_release/restore_assets.py',
    'scripts/access_release/install.py',
    'infra/backend/tests/test_backup_restore_contract.py', 'infra/backend/tests/test_access_release.py',
    'scripts/router_release/prepare_audit_restore.py', 'scripts/router_release/test_prepare_audit_restore.py',
    'scripts/router_release/prepare_recovery_release.py',
    'scripts/tests/test_router_backup.py',
    'scripts/tests/test_bootstrap_checkout.py',
    'docs/router-disaster-restore.md',
)


def audit_export_test(target):
    path=target/'scripts/router_release/test_activate.py'
    extra='''    def test_lab_export_failure_does_not_rollback_verified_production(self):
        fake_spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
        exporter = SimpleNamespace(main=unittest.mock.Mock(side_effect=RuntimeError('fixture export failure')))
        with patch.object(activate, 'KIT', self.kit), patch.object(core, 'STATE', self.kit / 'private/no-transition'), patch.object(activate.os, 'geteuid', return_value=0), patch.object(core, 'platform', return_value=Platform), patch.object(core, 'verify', return_value={}), patch.object(core, 'guard_runtime'), patch.object(activate, 'prepare_tools'), patch.object(activate, 'probe_settings', return_value={}), patch.object(activate, 'ensure_repository', return_value=SimpleNamespace(smoke=lambda: {'ok': True})), patch.object(activate, 'candidate_settings', return_value={}), patch.object(activate, 'RouterRepository'), patch.object(activate, 'install_hooks', return_value=self.kit / 'private/pending'), patch.object(core, 'deploy'), patch.object(activate, 'full_proof', return_value={}), patch.object(activate, 'resume_timers') as resume, patch.object(core, 'rollback') as rollback, patch('importlib.util.spec_from_file_location', return_value=fake_spec), patch('importlib.util.module_from_spec', return_value=exporter):
            activate.main()
            rollback.assert_not_called()
            resume.assert_called_once()
        result=json.loads((self.kit/'evidence/router-live-acceptance.json').read_text())
        self.assertTrue(result['ok']);self.assertFalse(result['audit_input_prepared'])

'''
    path.write_text(builder.replace_once(path.read_text(), '    def test_requires_real_sudo_before_any_operation(self):',
        extra+'    def test_requires_real_sudo_before_any_operation(self):'))


def activation_tests(target):
    path = target / 'scripts/router_release/test_activate.py'
    text = builder.replace_once(path.read_text(),
        'self.settings.update(restic_enabled=False, ai_weekly_backup_enabled=False)',
        'self.settings.update(restic_enabled=True, ai_weekly_backup_enabled=True)')
    extra = '''    def test_operator_disabled_weekly_schedule_is_preserved(self):
        self.settings['ai_weekly_backup_enabled'] = False
        (self.base / 'backups/backup_settings.json').write_text(json.dumps(self.settings))
        with patch.object(activate, 'BASE', self.base), patch.object(activate, 'KIT', self.kit), patch.object(core, 'platform', return_value=Platform):
            self.assertFalse(activate.candidate_settings(self.settings)['ai_weekly_backup_enabled'])

    def test_operator_disabled_router_backup_is_not_silently_enabled(self):
        self.settings['restic_enabled'] = False
        (self.base / 'backups/backup_settings.json').write_text(json.dumps(self.settings))
        with patch.object(activate, 'BASE', self.base), patch.object(activate, 'KIT', self.kit), patch.object(core, 'platform', return_value=Platform):
            with self.assertRaises(ValueError): activate.candidate_settings(self.settings)

'''
    text = builder.replace_once(text, '    def test_requires_real_sudo_before_any_operation(self):',
                                extra + '    def test_requires_real_sudo_before_any_operation(self):')
    path.write_text(text)
    audit_export_test(target)


def source():
    if KIT.exists():
        raise ValueError('Never overwrite a prepared or sealed release')
    if json.loads((BASE / 'infra/access-release.json').read_text())['release'] != OLD:
        raise ValueError('Active baseline changed')
    prior = BASE / 'backups/releases' / OLD
    manifest = json.loads((prior / 'release.json').read_text())
    for relative, sha in manifest['source_sha256'].items():
        if builder.digest(prior / 'source' / relative) != sha:
            raise ValueError('Sealed baseline changed')
    rows = json.loads(subprocess.check_output(['docker', 'inspect', *manifest['baseline']]))
    KIT.mkdir()
    for name in ('source', 'evidence', 'tools', 'private'):
        if name != 'source':
            (KIT / name).mkdir(mode=0o700 if name == 'private' else 0o755)
    target = KIT / 'source'
    shutil.copytree(prior / 'source', target, ignore=shutil.ignore_patterns('__pycache__'))
    for relative in FILES:
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / relative, target / relative)
    shutil.copyfile(BASE / 'scripts/router_release/bootstrap_restore_candidate.sh', target / 'scripts/bootstrap_restore_v0_1.sh')
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.sh', '.service', '.timer', '.path', '.conf', '.json'):
            text = path.read_text()
            if OLD in text:
                path.write_text(text.replace(OLD, NAME))
    deploy = target / 'scripts/f10_release/deploy.py'
    deploy.write_text(builder.replace_once(deploy.read_text(),
        "OLD='hc-router-backup-20261101-r14'", 'OLD=' + repr(OLD)))
    activation = target / 'scripts/router_release/activate.py'
    text = activation.read_text().replace('router-r15', 'router-r16').replace("say('r15:", "say('r16:")
    old = """    from resume_policy import resume_weekly
    containment = json.loads((KIT / 'evidence/incident-containment.json').read_text())
    result = resume_weekly(current, result, containment)"""
    new = """    if current.get('backup_target') != 'router_ftp' or current.get('restic_enabled') is not True:
        raise ValueError('Expected active r15 router backup; preserve operator-disabled schedules')
    result['ai_weekly_backup_enabled'] = current.get('ai_weekly_backup_enabled') is True"""
    text = builder.replace_once(text, old, new)
    text = builder.replace_once(text, '            resume_timers(candidate, pending)',
        """            say('Az ellenőrzött mentés privát laborbemenetének előkészítése.')
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location('audit_export', SOURCE / 'scripts/router_release/prepare_audit_restore.py')
                exporter = importlib.util.module_from_spec(spec); spec.loader.exec_module(exporter)
                result['audit_input_prepared'] = exporter.main() == 0
            except Exception as error:
                result['audit_input_prepared'] = False
                write(KIT / 'private/audit-input-error.json', {'error_type': type(error).__name__})
            resume_timers(candidate, pending)""")
    activation.write_text(text)
    activation_tests(target)
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
        scope=['Frozen recovery helper selection, offline HA image alias and checked Git export index; AI remains disabled'],
        status='preparing_recovery_export_corrections', live_transport_proof='live-transport-proof.json')
    (KIT / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(prior / 'tools/rclone', KIT / 'tools/rclone')
    (KIT / 'tools/rclone').chmod(0o755)
    shutil.copyfile(prior / 'evidence/router-live-acceptance.json', KIT / 'evidence/live-transport-proof.json')


def seal():
    evidence=KIT/'evidence'
    proof=json.loads((evidence/'restore-acceptance/vm-acceptance.json').read_text())
    equivalence=json.loads((evidence/'vm-source-equivalence.json').read_text())
    required=('ok','reboot_verified','repeated_unit_bytes_identical',
              'unavailable_repository_preserves_live_state','offline_homeassistant_verified',
              'root_ipc_verified','five_timers_verified')
    if not all(proof.get(key) is True for key in required):
        raise ValueError('Full fresh/repeated/reboot/offline repository acceptance required')
    if not equivalence.get('ok') or equivalence['candidate_git_commit'] != proof['fresh']['git_commit']:
        raise ValueError('VM correction and release source differ')
    for name in ('recovery-assets-tests.log','export-restore-tests.log',
                 'audit-preparation-tests.log','bootstrap-permissions-tests.log'):
        if '\nOK' not in (evidence/name).read_text():raise ValueError('Missing successful '+name)
    if not json.loads((evidence/'public-export-index.json').read_text())['ok']:
        raise ValueError('Real public export index check required')
    baked=json.loads((evidence/'baked-modules.json').read_text())
    if not baked['ok'] or any(builder.digest(KIT/'source/infra/backend'/name)!=sha
                              for name,sha in baked['baked_module_sha256'].items()):
        raise ValueError('Baked backend modules changed after verification')
    builder.seal()
    manifest=json.loads((KIT/'release.json').read_text())
    manifest.update(status='recovery_export_fix_ready_local_sudo_required',
                    full_vm_candidate_restore_verified=True)
    (KIT/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')


spec = importlib.util.spec_from_file_location('router_builder', Path(__file__).with_name('prepare.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
builder.OLD, builder.NAME, builder.KIT = OLD, NAME, KIT

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('source', 'build', 'seal'))
    args = parser.parse_args()
    {'source': source, 'build': builder.build, 'seal': seal}[args.action]()
