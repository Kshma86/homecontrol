#!/usr/bin/env python3
"""Router repository setup/check/restore; normal worker shares the host runner lock."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infra/backend'))
from backup_protocol import RUN_ID, read_json, target
from router_backup import DEFAULTS, RouterRepository
from router_operation_log import OperationLog


class RetentionFailed(RuntimeError):
    pass


@contextmanager
def lock(root, worker):
    path = root / 'homecontrol-backup.lock'
    if worker:
        run_id = os.environ.get('HC_BACKUP_RUN_ID', '')
        if not RUN_ID.fullmatch(run_id):
            raise ValueError('Worker must be called by the common runner')
        fd = int(os.environ['HC_BACKUP_LOCK_FD'])
        info, expected = os.fstat(fd), path.stat()
        if (info.st_dev, info.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError('Wrong inherited backup lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    else:
        root.mkdir(parents=True, exist_ok=True)
        with path.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'smoke', 'backup', 'check', 'restore'))
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('BACKUP_ROOT', '/srv/docker/homecontrol/backups')))
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--source', action='append', default=[])
    parser.add_argument('--exclude', action='append', default=[])
    parser.add_argument('--snapshot', help='Full snapshot ID for staging restore')
    parser.add_argument('--staging', type=Path, help='Existing empty directory for restore')
    parser.add_argument('--secrets-root', type=Path, help='Decrypted emergency bundle root (restore only)')
    args = parser.parse_args()
    if args.action == 'backup' and not args.worker:
        parser.error('Backups must use the common host runner')
    settings_path = args.settings or Path(os.environ.get('HC_BACKUP_SETTINGS_FILE', args.root / 'backup_settings.json'))
    settings = read_json(settings_path)
    if settings is None:
        parser.error('A valid explicit settings file is required')
    settings = {**DEFAULTS, **settings}
    if args.secrets_root:
        if args.action != 'restore':
            parser.error('--secrets-root is only supported for staging restore')
        for key in ('router_rclone_config', 'restic_password_file'):
            original = Path(settings[key])
            if not original.is_absolute() or '..' in original.parts:
                parser.error('Invalid emergency credential path')
            settings[key] = str(args.secrets_root / original.relative_to('/'))
    with lock(args.root, args.worker), tempfile.TemporaryDirectory(prefix='hc-router-restic-') as work:
        run_id = os.environ.get('HC_BACKUP_RUN_ID', '')
        diagnostics = OperationLog(args.root, run_id if args.worker else uuid.uuid4().hex)
        repo = RouterRepository(settings, run=diagnostics, cache=Path(work) / 'cache')
        def state(name, value, detail=''):
            if args.worker:
                target(args.root, run_id, name, value, detail)
        if args.action == 'backup':
            state('restic', 'running')
            try:
                if not args.source:
                    raise ValueError('No backup sources supplied')
                # The first source is the completed local archive, never a partial tar.
                from backup_protocol import verify_archive
                archive = Path(args.source[0])
                receipt = read_json(str(archive) + '.complete.json')
                if not receipt or receipt.get('completed') is not True:
                    raise ValueError('A completed local archive receipt is required')
                checked = verify_archive(archive)
                if checked['sha256'] != receipt.get('sha256'):
                    raise ValueError('Local archive no longer matches its receipt')
                snapshot_id = repo.backup(args.source, excludes=args.exclude)
                state('restic', 'succeeded', 'Snapshot ' + snapshot_id)
            except Exception:
                detail = 'Router snapshot failed; local archive retained'
                if diagnostics.last_failure:
                    failure = diagnostics.last_failure
                    detail += '; {} {} exit {}'.format(failure['tool'], failure['operation'], failure['exit_code'])
                if diagnostics.record_failed:
                    detail += '; private diagnostic write failed'
                state('restic', 'failed', detail)
                raise
            state('restic_retention', 'running')
            try:
                repo.retention()
                state('restic_retention', 'succeeded')
            except Exception:
                state('restic_retention', 'failed', 'Snapshot created; retention failed')
                raise RetentionFailed('Snapshot created; retention failed')
            print(json.dumps({'ok': True, 'snapshot_id': snapshot_id}))
        elif args.action == 'check':
            state('restic_check', 'running')
            try:
                repo.check()
                state('restic_check', 'succeeded', 'Full encrypted data read verified')
            except Exception:
                state('restic_check', 'failed', 'Router integrity check failed')
                raise
        elif args.action == 'init':
            repo.init()
            print('Repository initialized. Save the restic password outside the HC machine.')
        elif args.action == 'smoke':
            # Probe only a purpose-named test repository, never the production namespace.
            if not re.fullmatch(r'/[^/]+/hc-backup/probes/[A-Za-z0-9_-]+', settings['router_repository_path']):
                raise ValueError('Smoke requires /<disk>/hc-backup/probes/<unique-name>')
            print(json.dumps(repo.smoke(), indent=2))
        else:
            if not args.snapshot or args.staging is None:
                parser.error('Restore requires --snapshot and --staging')
            repo.prepare()
            from restore_archive import snapshot
            selected = snapshot(repo.snapshots(), args.snapshot)
            repo.restore(selected, args.staging)
            print(json.dumps({'ok': True, 'snapshot_id': selected, 'staging': str(args.staging)}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Avoid echoing server messages, user-provided credentials or raw command output.
        print('Router operation failed ({}). Check the target settings, credentials and repository.'.format(type(error).__name__), file=sys.stderr)
        raise SystemExit(2 if isinstance(error, RetentionFailed) else 1)
