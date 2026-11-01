#!/usr/bin/env python3
"""Compare the deployed listing with serialized FTP, then prove a pinned restore."""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

from diagnose import expected_packs, HEX

BASE = Path('/srv/docker/homecontrol')
RELEASE = 'hc-router-backup-20261101-r14'


def command(original, serialized):
    result = [original[0], '--no-lock', *original[1:]]
    if serialized:
        position = next(i for i, value in enumerate(result) if value.startswith('rclone.args='))
        result[position] += ' --checkers 1 --transfers 1'
        result.extend(['-o', 'rclone.connections=2'])
    return result


def compare(repo, expected, report):
    original = list(repo.command)
    for label, serialized in [('deployed', False), ('serialized', True)]:
        repo.command = command(original, serialized)
        report['phase'] = label + '_listing'
        result = report.setdefault(label, {})
        try:
            output = repo.call(['list', 'packs'])
            listed = {line.strip() for line in output.splitlines() if HEX.fullmatch(line.strip())}
            result.update(listed_pack_count=len(listed), missing_pack_count=len(expected - listed),
                          unexpected_pack_count=len(listed - expected))
            if listed != expected:
                if serialized:
                    raise ValueError('Serialized transport inventory mismatch')
                continue
            report['phase'] = label + '_check'
            repo.call(['check', '--read-data'] if serialized else ['check'])
            result['check'] = 'full_data_verified' if serialized else 'metadata_verified'
        except Exception as error:
            result['error_type'] = type(error).__name__
            if serialized:
                raise
    report['serialized_verified'] = True


def main():
    if os.geteuid() != 0:
        raise PermissionError('Local sudo required for private router credentials')
    sys.dont_write_bytecode = True
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    kit = BASE / 'backups/releases' / RELEASE
    runtime = BASE / 'scripts/access_runtime' / RELEASE
    if json.loads((BASE / 'infra/access-release.json').read_text()).get('release') != RELEASE:
        raise ValueError('This proof requires active r14')
    manifest = json.loads((kit / 'release.json').read_text())
    for name in ('infra/backend/router_backup.py', 'infra/backend/backup_protocol.py',
                 'scripts/restore_smoke.py', 'scripts/restore_archive.py'):
        if hashlib.sha256((runtime / name).read_bytes()).hexdigest() != manifest['source_sha256'][name]:
            raise ValueError('Frozen proof module changed')
    sys.path.insert(0, str(runtime / 'infra/backend'))
    sys.path.insert(0, str(runtime / 'scripts'))
    from router_backup import RouterRepository, private_text
    from restore_smoke import verify, database_probe
    from restore_archive import prepare_database, snapshot

    settings = json.loads(private_text(BASE / 'backups/backup_settings.json'))
    if settings.get('restic_enabled') or settings.get('ai_weekly_backup_enabled'):
        raise ValueError('Keep router backups suspended during proof')
    if (settings.get('backup_target') != 'router_ftp'
            or settings.get('router_repository_path') != '/G/hc-backup/restic/homecontrol'):
        raise ValueError('Unexpected repository')
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    log_path = kit / 'private' / ('router-transport-' + identifier + '.log')
    report_path = kit / 'evidence' / ('router-transport-' + identifier + '.json')
    report = {'release': RELEASE, 'ok': False, 'remote_write_commands': 0,
              'started_at': datetime.now(timezone.utc).isoformat(), 'phase': 'prepare'}
    with (BASE / 'backups/homecontrol-backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as log, tempfile.TemporaryDirectory(prefix='hc-router-transport-') as temporary:
            work = Path(temporary)
            def run(args, **kwargs):
                should_check = kwargs.pop('check', False)
                kwargs.setdefault('capture_output', True)
                kwargs.setdefault('text', True)
                result = subprocess.run(args, check=False, **kwargs)
                log.write('\nPhase: ' + report['phase'] + '\n')
                log.write(result.stdout or '')
                log.write(result.stderr or '')
                log.flush()
                if should_check and result.returncode:
                    raise RuntimeError('Proof subprocess failed')
                return result
            try:
                repo = RouterRepository(settings, run=run, cache=work / 'cache')
                repo.prepare()
                # Decrypt metadata again under the same lock; never use stale inventories.
                repo.command = [repo.command[0], '--no-lock', *repo.command[1:]]
                indexes = {}
                for name in repo.call(['list', 'index']).splitlines():
                    name = name.strip()
                    if not HEX.fullmatch(name) or len(indexes) >= 128:
                        raise ValueError('Unexpected index inventory')
                    indexes[name] = json.loads(repo.call(['cat', 'index', name]))
                expected = expected_packs(indexes)
                if not expected:
                    raise ValueError('No indexed packs')
                report['indexed_pack_count'] = len(expected)
                # compare() adds --no-lock itself.
                repo.command.remove('--no-lock')
                print('Eredeti listázás ellenőrzése, majd egy listázó szállal teljes visszaolvasás.', flush=True)
                compare(repo, expected, report)
                report['phase'] = 'pinned_archive_restore'
                pinned = snapshot(repo.snapshots())
                report['snapshot_id'] = pinned
                restored = work / 'restored'; restored.mkdir()
                repo.restore(pinned, restored, include=str(BASE / 'backups/homecontrol_*.tar.gz'))
                from restore_archive import latest_archive
                archive = latest_archive(restored / (BASE / 'backups').relative_to('/'))
                archive_proof = verify(archive)
                # Compare the restored tar to its original publication receipt as well.
                receipt = json.loads((BASE / 'backups' / (archive.name + '.complete.json')).read_text())
                if not receipt.get('completed') or archive_proof['sha256'] != receipt.get('sha256'):
                    raise ValueError('Restored archive differs from its published local receipt')
                report['archive_sha256'] = archive_proof['sha256']
                report['archive_verified_files'] = archive_proof['verified_files']
                report['archive_restore'] = 'sha256_verified'
                report['phase'] = 'isolated_postgres_restore'
                image = run(['docker', 'inspect', 'homecontrol-postgres', '--format', '{{.Image}}'], check=True).stdout.strip()
                if not image.startswith('sha256:'):
                    raise ValueError('Could not pin the existing PostgreSQL image')
                os.environ['HC_RESTORE_POSTGRES_IMAGE'] = image
                dump = prepare_database(archive, work / 'database')
                database_probe(dump['dump'], run=run)
                report['database'] = 'isolated_restore_verified'
                report['phase'] = 'completed'
                report['ok'] = True
            except Exception as error:
                report['error_type'] = type(error).__name__
                print('A próba megállt. Privát napló: ' + str(log_path), flush=True)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['automatic_router_backup_enabled'] = False
        fd = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'w') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BlockingIOError:
        raise SystemExit('Másik mentés fut; a próba nem indult el.')
    except Exception as error:
        raise SystemExit('A próba nem indult el: ' + type(error).__name__)
