#!/usr/bin/env python3
"""One local sudo command: private FTP setup, probe, guarded cutover and restore proof."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-containers-20261103-r23'
KIT = BASE / 'backups/releases' / NAME
SOURCE = KIT / 'source'
sys.path.insert(0, str(SOURCE / 'scripts/f10_release'))
import deploy as core
sys.path.insert(0, str(SOURCE / 'infra/backend'))
from router_backup import DEFAULTS, RouterRepository, private_text, repository, validate, require_rclone

EXTRA_TARGETS = ('backups/backup_settings.json', 'docs/router-backup-settings.json')
TIMER_NAMES = ('homecontrol-backup.timer', 'homecontrol-ai-weekly-backup.timer',
               'homecontrol-restic-check.timer', 'homecontrol-log-maintenance.timer')


def say(message):
    print(message, flush=True)


def write(path, value):
    core.platform().write_json(path, value, 0o600)


def prepare_tools():
    tool = KIT / 'tools/rclone'
    if core.digest(tool) != core.load()['rclone_sha256']:
        raise ValueError('Pinned rclone changed')
    target = Path('/usr/local/bin/rclone')
    if target.exists() or target.is_symlink():
        if target.is_symlink() or core.digest(target) != core.digest(tool):
            raise ValueError('Inspect existing /usr/local/bin/rclone before replacing it')
    else:
        with tempfile.NamedTemporaryFile(prefix='.hc-rclone-', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                with tool.open('rb') as source:
                    shutil.copyfileobj(source, stream)
                stream.flush(); os.fsync(stream.fileno()); temporary.chmod(0o755)
                os.link(temporary, target)  # exclusive publication, no replacement
            finally:
                temporary.unlink(missing_ok=True)
    os.environ['PATH'] = '/usr/local/bin:' + os.environ.get('PATH', '')
    require_rclone()


def probe_settings():
    output = KIT / 'private/router-probe-settings.json'
    config = Path(DEFAULTS['router_rclone_config'])
    password = Path('/etc/homecontrol/router-restic-password')
    if not config.exists():
        if output.exists():
            raise ValueError('Probe settings exist without credentials; reconcile before retry')
        say('Router FTP-jelszó megadása a helyi terminálon:')
        subprocess.run([sys.executable, str(SOURCE / 'scripts/configure_router_backup.py'),
                        '--host', '192.168.1.1', '--user', 'kshma', '--mount', '/G',
                        '--repository-path', '/G/hc-backup/probes/router-r22',
                        '--settings-out', str(output)], check=True)
    elif not output.exists():
        private_text(config); private_text(password)
        write(output, {**DEFAULTS, 'backup_target': 'router_ftp', 'restic_password_file': str(password),
                       'router_repository_path': '/G/hc-backup/probes/router-r22'})
    settings = json.loads(output.read_text())
    validate(settings)
    if settings['router_repository_path'] != '/G/hc-backup/probes/router-r22':
        raise ValueError('Unexpected probe repository')
    return settings


def ensure_repository(settings):
    """Activation explicitly initializes a new target; ordinary backups never do."""
    repo = RouterRepository(settings)
    repo.prepare()
    try:
        repo.call(['snapshots', '--json'], timeout=120)
    except RuntimeError:
        # init refuses an existing repository, including one with an incorrect key.
        repo.init()
    return repo


def candidate_settings(probe):
    current = json.loads((BASE / 'backups/backup_settings.json').read_text())
    result = {**current, **{key: probe[key] for key in DEFAULTS if key.startswith('router_')}}
    result.update(backup_target='router_ftp', restic_enabled=True,
                  restic_password_file=probe['restic_password_file'],
                  router_repository_path='/G/hc-backup/restic/homecontrol',
                  git_origin_enabled=False, include_gitea=False, ai_weekly_shutdown_after=False)
    validate(result)
    result['restic_repository'] = repository(result)
    if not result.get('git_enabled') or not result.get('git_offsite_enabled') or not result.get('git_offsite_remote'):
        raise ValueError('The approved existing external Git target must be preserved')
    for key in ('git_offsite_remote', 'git_offsite_branch', 'git_offsite_ssh_key', 'git_offsite_token_file'):
        if result.get(key) != current.get(key):
            raise ValueError('External Git destination changed')
    if current.get('backup_target') != 'router_ftp' or current.get('restic_enabled') is not True:
        raise ValueError('Expected active r15 router backup; preserve operator-disabled schedules')
    result['ai_weekly_backup_enabled'] = current.get('ai_weekly_backup_enabled') is True
    write(KIT / 'private/router-settings.json', result)
    return result


def install_hooks(candidate):
    """Extend the existing tested cutover transaction, including exact rollback files."""
    original_targets = core.target_files
    original_install = core.install_files
    original_verify = core.Cutover.verify
    original_resume = core.Cutover.resume
    pending = KIT / 'private/router-proofs-pending.json'
    core.ROUTER_SETTINGS = candidate

    def targets():
        extra = [BASE / name for name in EXTRA_TARGETS]
        extra += [core.UNIT_ROOT / name for name in TIMER_NAMES]
        extra += [core.UNIT_ROOT / 'timers.target.wants' / name for name in TIMER_NAMES]
        return list(dict.fromkeys(original_targets() + extra))

    def install(manifest):
        original_install(manifest)
        core.atomic_copy(KIT / 'private/router-settings.json', BASE / 'backups/backup_settings.json')
        (BASE / 'backups/backup_settings.json').chmod(0o600)
        public = {key: candidate[key] for key in DEFAULTS if key.startswith('router_')}
        public.update(backup_target='router_ftp', restic_password_file=candidate['restic_password_file'])
        core.platform().write_json(BASE / 'docs/router-backup-settings.json', public, 0o644)
        manifest_path = BASE / 'secrets/manifest.txt'
        lines = manifest_path.read_text().splitlines()
        for key in ('router_rclone_config', 'restic_password_file'):
            if candidate[key] not in lines:
                lines.append(candidate[key])
        manifest_path.write_text('\n'.join(lines) + '\n')

    def verify(context):
        original_verify(context)
        write(pending, {'release': NAME, 'state': 'awaiting_router_backup_restore'})

    def resume(context):
        if not pending.exists():
            original_resume(context)

    core.target_files = targets
    core.install_files = install
    core.Cutover.verify = verify
    core.Cutover.resume = resume
    return pending


def full_proof(manifest):
    say('Teljes HC + Git + router mentés indul. Ez néhány percig tarthat.')
    core.phase('router_full_backup')
    previous = json.loads((BASE / 'backups/backup-state.json').read_text()).get('run_id')
    core.call([sys.executable, str(core.RUNTIME / 'scripts/hostops/backup_runner.py'), '--mode', 'weekly'], timeout=7200)
    state = json.loads((BASE / 'backups/backup-state.json').read_text())
    if state.get('run_id') == previous or state.get('state') != 'completed' or state.get('scope') != 'router':
        raise ValueError('No new completed router backup')
    for name in ('local_archive', 'restic', 'git_offsite', 'secrets_bundle'):
        if state.get('targets', {}).get(name, {}).get('state') != 'succeeded':
            raise ValueError('Required backup target did not complete: ' + name)
    write(KIT / 'private/router-full-backup.json', state)
    say('Mentés kész. Visszaolvasás és külön PostgreSQL-visszaállítási próba indul.')
    core.phase('router_restore_proof')
    core.call([sys.executable, str(core.RUNTIME / 'scripts/restore_smoke.py'), '--db-check'], timeout=7200,
              extra_env={'HC_RESTORE_POSTGRES_IMAGE': manifest['baseline']['homecontrol-postgres']['image']})
    smoke = json.loads((BASE / 'backups/restore-smoke-result.json').read_text())
    if not (smoke.get('ok') and smoke.get('restic') == 'sha256_verified'
            and smoke.get('database') == 'restore_verified_without_owner_acl'):
        raise ValueError('Router filesystem/database restore proof failed')
    write(KIT / 'private/router-restore-proof.json', smoke)
    status = core.request('/api/deployment/status')
    if status.get('ai_enabled') is not False or status.get('router_backup_enabled') is not True:
        raise ValueError('AI-offline/router policy acceptance failed')
    core.wait_ready(manifest)
    return {'run_id': state['run_id'], 'snapshot_id': smoke['snapshot_id'],
            'git': 'pushed', 'restore': 'verified', 'database': 'verified', 'ai_enabled': False}


def resume_timers(candidate, pending):
    sys.path.insert(0, str(core.RUNTIME / 'scripts'))
    from install_backup_f6 import schedule_units, unit_sources
    units, enabled = schedule_units(unit_sources(), candidate)
    for name in TIMER_NAMES:
        target = core.UNIT_ROOT / name
        core.platform().no_symlinks(target)
        target.write_text(units[name]); target.chmod(0o644)
    core.call(['systemctl', 'daemon-reload'])
    for name in TIMER_NAMES:
        core.call(['systemctl', 'enable' if enabled[name] else 'disable', name])
    transition = json.loads((core.STATE / 'transition.json').read_text())
    pending.unlink(missing_ok=True)
    for name, wanted in transition['active_timers'].items():
        if name in enabled:
            wanted = enabled[name]
        if wanted:
            core.call(['systemctl', 'start', name])
    for name in TIMER_NAMES:
        if enabled[name] and not core.active(name):
            raise ValueError('Scheduled backup timer is not active: ' + name)


def main(action='activate'):
    if os.geteuid() != 0:
        raise PermissionError('Start this command with sudo in the HC local terminal')
    operator = KIT / 'private/router-operator.lock'
    core.platform().no_symlinks(operator)
    with operator.open('a') as handle:
        core.fcntl.flock(handle, core.fcntl.LOCK_EX | core.fcntl.LOCK_NB)
        manifest = core.verify()
        if action == 'rollback':
            # Exact snapshot restores settings, units and enablement symlinks too.
            # Hooks only add targets for initial snapshot; rollback reads its recorded list.
            core.rollback(manifest)
            say('Visszaállítás kész.')
            return
        if core.STATE.exists():
            raise ValueError('A transition already exists; inspect the receipt before repeating activation')
        core.guard_runtime(manifest)
        say('r22: rclone telepítése az ellenőrzött helyi csomagból.')
        prepare_tools()
        probe = probe_settings()
        say('Titkosított router-próba és SHA-256 visszaellenőrzés indul.')
        repo = ensure_repository(probe)
        proof = repo.smoke()
        write(KIT / 'private/router-smoke.json', proof)
        say('Router-próba sikeres. A végleges cél előkészítése indul.')
        candidate = candidate_settings(probe)
        say('Bármilyen átállítás előtt teljes éles repository-ellenőrzés indul.')
        RouterRepository(candidate).check()
        pending = install_hooks(candidate)
        switched = False
        try:
            say('Ellenőrzött helyi mentés, majd backend, mDNS, Growatt és host mentő átállítása.')
            core.deploy()
            switched = True
            result = full_proof(manifest)
            say('Az ellenőrzött mentés privát laborbemenetének előkészítése.')
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location('audit_export', SOURCE / 'scripts/router_release/prepare_audit_restore.py')
                exporter = importlib.util.module_from_spec(spec); spec.loader.exec_module(exporter)
                result['audit_input_prepared'] = exporter.main() == 0
            except Exception as error:
                result['audit_input_prepared'] = False
                write(KIT / 'private/audit-input-error.json', {'error_type': type(error).__name__})
            resume_timers(candidate, pending)
            result.update(ok=True, release=NAME, state='deployed_and_router_restore_verified')
            core.platform().write_json(KIT / 'evidence/router-live-acceptance.json', result, 0o644)
            core.platform().write_json(KIT / 'deployment-status.json', result, 0o644)
            say(json.dumps(result, ensure_ascii=False, indent=2))
        except BaseException:
            if switched:
                say('Az átvételi próba hibás; az előző kiadás visszaállítása indul.')
                core.rollback(manifest)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('activate', 'rollback'), nargs='?', default='activate')
    args = parser.parse_args()
    try:
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
        main(args.action)
    except BaseException as error:
        if os.geteuid() == 0:
            core.platform().write_json(KIT / 'private/router-error.json', {'error_type': type(error).__name__, 'detail': str(error)})
        raise SystemExit('A routeres élesítés megállt ({}). Napló: private/router-error.json; a jelszót ne küldd el.'.format(type(error).__name__))
