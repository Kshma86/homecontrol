#!/usr/bin/env python3
"""Export explicit private lab inputs; read production router/Git without modifying them."""
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import stat
import subprocess
import sys
from zoneinfo import ZoneInfo

BASE = Path('/srv/docker/homecontrol')
RELEASE = 'hc-security-20261102-r18'
INPUT = Path('/tmp/hc-security-audit-20261102/input')
EVIDENCE = BASE / 'docs/audit-evidence/hc23-43-20261102/live-restore-input'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def log_result(stream, result):
    if isinstance(result.stdout, bytes):
        stream.write('Binary output: {} bytes\n'.format(len(result.stdout)))
    else:
        stream.write(result.stdout or '')
    error = result.stderr or ''
    stream.write(error.decode(errors='replace') if isinstance(error, bytes) else error)
    stream.flush()


def recovery_key(path, operator_uid):
    """The offline identity may belong to root or the explicitly named operator."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or info.st_uid not in (0, operator_uid)):
            raise ValueError('Recovery identity must be private and owned by root or the operator')
        value = stream.read(65537)
        if not value.strip() or len(value) > 65536:
            raise ValueError('Empty or oversized recovery identity')
        return value


def export_inputs(report, kit, operator_uid, archive_receipt):
    key = recovery_key(BASE / 'infra/ssh/homecontrol-secrets-age-key.txt', operator_uid)
    # An existing key is never replaced, even on an explicitly resumed export.
    fd = os.open(INPUT / 'age-key.txt', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(key)
    shutil.copyfile(BASE / 'docs/router-backup-settings.json', INPUT / 'router-settings.json')
    shutil.copyfile(kit / 'tools/rclone', INPUT / 'rclone')
    (INPUT / 'rclone').chmod(0o755)
    report.update(rclone_sha256=digest(INPUT / 'rclone'), archive_receipt=archive_receipt,
                  private_input=str(INPUT), phase='ready_for_isolated_restore', ok=True)
    report.pop('error_type', None)


def finish_export():
    """Resume just the failed operator-key export; do not contact router or Git."""
    os.umask(0o077)
    operator = pwd.getpwnam('a')
    if os.geteuid() != operator.pw_uid:
        raise PermissionError('Finish this delegated export as the requesting operator')
    marker = json.loads((BASE / 'infra/access-release.json').read_text())
    if marker.get('release') != RELEASE:
        raise ValueError('Active release changed')
    for path in (INPUT, INPUT / 'input.json', INPUT / 'git.git'):
        if path.is_symlink() or path.stat().st_uid != operator.pw_uid:
            raise ValueError('Expected private operator-owned lab export')
    report = json.loads((INPUT / 'input.json').read_text())
    if (report.get('ok') or report.get('release') != RELEASE
            or report.get('phase') != 'export_private_recovery_input'
            or report.get('repository_check') != 'full_data_verified'
            or report.get('git_objects') != 'verified'
            or report != json.loads((EVIDENCE / 'input-preparation.json').read_text())):
        raise ValueError('No matching verified export to resume')
    commit = subprocess.check_output(['git', '--git-dir', str(INPUT / 'git.git'),
                                     'rev-parse', 'refs/heads/main'], text=True).strip()
    bundle = subprocess.check_output(['git', '--git-dir', str(INPUT / 'git.git'), 'show',
        commit + ':secrets/homecontrol-secrets-latest.tar.gz.age'])
    if commit != report['git_commit'] or hashlib.sha256(bundle).hexdigest() != report['git_bundle_sha256']:
        raise ValueError('Delegated Git copy changed')
    kit = BASE / 'backups/releases' / RELEASE
    live = json.loads((kit / 'evidence/post-live-check.json').read_text())
    if live['live_acceptance']['snapshot_id'] != report['snapshot_id']:
        raise ValueError('Cannot associate the archived receipt with this snapshot')
    report['resumed_at'] = datetime.now(ZoneInfo('Europe/Budapest')).isoformat()
    report['resume_scope'] = 'operator_owned_private_identity_and_public_tools_only'
    export_inputs(report, kit, operator.pw_uid, live['backup_state']['archive'])
    report['finished_at'] = datetime.now(ZoneInfo('Europe/Budapest')).isoformat()
    sys.path.insert(0, str(Path(marker['runtime']) / 'infra/backend'))
    from backup_protocol import atomic_json
    atomic_json(INPUT / 'input.json', report, 0o600)
    atomic_json(EVIDENCE / 'input-preparation.json', report, 0o644)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main():
    if os.geteuid() != 0:
        raise PermissionError('Local sudo is required to export the recovery key for the isolated lab')
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    sys.dont_write_bytecode = True
    marker = json.loads((BASE / 'infra/access-release.json').read_text())
    if marker.get('release') != RELEASE:
        raise ValueError('Expected reviewed r15 release')
    kit = BASE / 'backups/releases' / RELEASE
    runtime = Path(marker['runtime'])
    manifest = json.loads((kit / 'release.json').read_text())
    for name in ('infra/backend/router_backup.py', 'scripts/restore_archive.py'):
        if digest(runtime / name) != manifest['source_sha256'][name]:
            raise ValueError('Frozen recovery module changed')
    sys.path[:0] = [str(runtime / 'infra/backend'), str(runtime / 'scripts')]
    from router_backup import RouterRepository, private_text
    from restore_archive import snapshot
    from backup_protocol import atomic_json
    from access_release.common import no_symlinks
    no_symlinks(INPUT)
    if INPUT.exists():
        raise FileExistsError('Lab input exists; inspect it rather than overwriting it')
    operator = pwd.getpwnam('a')
    if not INPUT.parent.exists():
        INPUT.parent.mkdir(mode=0o700, parents=True)
        os.chown(INPUT.parent, operator.pw_uid, operator.pw_gid)
    if INPUT.parent.stat().st_uid not in (0, operator.pw_uid):
        raise ValueError('Lab parent must belong to root or the requesting operator')
    if shutil.disk_usage(INPUT.parent).free < 35 * 1024 ** 3:
        raise ValueError('At least 35 GiB free space is required for this restore lab')
    report = {'release': RELEASE, 'ok': False,
              'started_at': datetime.now(ZoneInfo('Europe/Budapest')).isoformat(),
              'remote_write_commands': 0, 'phase': 'prepare'}
    with (BASE / 'backups/homecontrol-backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        INPUT.mkdir(mode=0o700)
        with (INPUT / 'prepare.log').open('x') as log:
            def run(args, **kwargs):
                wanted = kwargs.pop('check', False)
                kwargs.setdefault('capture_output', True)
                kwargs.setdefault('text', True)
                result = subprocess.run(args, check=False, **kwargs)
                log.write('\nPhase: ' + report['phase'] + '\n')
                log_result(log, result)
                if wanted and result.returncode:
                    raise RuntimeError('Lab preparation command failed; inspect the private log')
                return result
            try:
                settings = json.loads(private_text(BASE / 'backups/backup_settings.json'))
                repo = RouterRepository(settings, run=run)
                repo.prepare()
                repo.command.insert(1, '--no-lock')
                pinned = snapshot(repo.snapshots())
                report['snapshot_id'] = pinned
                report['phase'] = 'copy_encrypted_router_repository'
                print('A titkosított routeres repository csak olvasó másolása a privát laborbemenetbe.', flush=True)
                remote = settings['router_rclone_remote'] + ':' + settings['router_repository_path']
                run(['rclone', 'copy', remote, str(INPUT / 'repository'), '--checkers', '1',
                     '--transfers', '1', '--multi-thread-streams', '0', '--retries', '1',
                     '--low-level-retries', '1'], env=repo.env, check=True, timeout=10800)
                report['phase'] = 'verify_local_repository'
                print('A letöltött teljes repository helyi adatellenőrzése.', flush=True)
                env = {key: value for key, value in os.environ.items()
                       if not key.startswith(('RESTIC_', 'RCLONE_'))}
                run(['restic', '-r', str(INPUT / 'repository'), '--password-file',
                     settings['restic_password_file'], 'check', '--read-data'],
                    env=env, check=True, timeout=10800)
                report['repository_check'] = 'full_data_verified'
                report['phase'] = 'read_external_git'
                print('A külső Git teljes, csak olvasó klónja és a titkosított bundle egyeztetése.', flush=True)
                remote = settings['git_offsite_remote']
                if remote != 'git@github.com:Kshma86/homecontrol.git':
                    raise ValueError('Unexpected external Git destination')
                env = {**env, 'GIT_TERMINAL_PROMPT': '0', 'GIT_SSH_COMMAND':
                       'ssh -i ' + shlex.quote(settings['git_offsite_ssh_key'])
                       + ' -o BatchMode=yes -o StrictHostKeyChecking=yes'}
                run(['git', 'clone', '--mirror', remote, str(INPUT / 'git.git')],
                    env=env, check=True, timeout=600)
                report['git_commit'] = run(['git', '--git-dir', str(INPUT / 'git.git'),
                    'rev-parse', 'refs/heads/main'], check=True).stdout.strip()
                bundle = run(['git', '--git-dir', str(INPUT / 'git.git'), 'show',
                    'refs/heads/main:secrets/homecontrol-secrets-latest.tar.gz.age'],
                    text=False, check=True)
                bundle_hash = hashlib.sha256(bundle.stdout).hexdigest()
                if bundle_hash != digest(BASE / 'secrets/homecontrol-secrets-latest.tar.gz.age'):
                    raise ValueError('Git recovery bundle differs from the current bundle')
                report['git_bundle_sha256'] = bundle_hash
                run(['git', '--git-dir', str(INPUT / 'git.git'), 'fsck', '--full'], check=True, timeout=600)
                report['git_objects'] = 'verified'
                report['phase'] = 'export_private_recovery_input'
                # Explicit operator-run export: no container reads a protected host key.
                state = json.loads((BASE / 'backups/backup-state.json').read_text())
                export_inputs(report, kit, operator.pw_uid, state.get('archive'))
            except Exception as error:
                report['error_type'] = type(error).__name__
        report['finished_at'] = datetime.now(ZoneInfo('Europe/Budapest')).isoformat()
        atomic_json(INPUT / 'input.json', report, 0o600)
        # Delegated to the requesting operator only, for transfer into a network-isolated VM.
        for path in sorted(INPUT.rglob('*'), reverse=True):
            if path.is_symlink():
                raise ValueError('Unexpected symlink in lab export')
            os.chown(path, operator.pw_uid, operator.pw_gid)
        os.chown(INPUT, operator.pw_uid, operator.pw_gid)
        atomic_json(EVIDENCE / 'input-preparation.json', report, 0o644)
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--finish-export']:
            raise SystemExit(finish_export())
        if len(sys.argv) != 1:
            raise ValueError('Unexpected arguments')
        raise SystemExit(main())
    except BlockingIOError:
        raise SystemExit('Another backup is running; no export started')
    except Exception as error:
        raise SystemExit('Lab export did not start: ' + type(error).__name__)
