"""Resume exactly the r21 precheck failure; remove only proven stale local locks."""
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import uuid

BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-audit-20261102-r21'
KIT = BASE / 'backups/releases' / NAME
SIDECAR = BASE / 'backups/releases/hc-audit-20261102-r21-continuation-1'
MANIFEST_SHA256 = 'd31eb653cafbaf8f3514e6e96690b013a3fd2410a5a70c28fece012593489f20'
sys.dont_write_bytecode = True


class ResumeError(ValueError):
    pass


def require(value, code):
    if not value:
        raise ResumeError(code)


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for data in iter(lambda: source.read(1024 ** 2), b''):
            result.update(data)
    return result.hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_sidecar():
    receipt = read(SIDECAR / 'acceptance.json')
    require(receipt.get('ok') is True, 'CONTINUATION_NOT_ACCEPTED')
    for name, expected in receipt['sha256'].items():
        path = SIDECAR / name
        require(not path.is_symlink() and digest(path) == expected, 'CONTINUATION_CHANGED')
    require(digest(KIT / 'release.json') == MANIFEST_SHA256, 'R21_MANIFEST_CHANGED')


def guard(core, manifest):
    require(read(KIT / 'private/audit-error.json') == {
        'error_type': 'RuntimeError',
        'detail': 'Restic operation failed (exit 1); repository was not reinitialized'},
        'UNEXPECTED_ORIGINAL_ERROR')
    require(not core.STATE.exists() and not core.RUNTIME.exists() and not core.PRIVATE.exists(), 'CUTOVER_ALREADY_STARTED')
    for name in ('runtime', 'baseline-runner', 'progress.json'):
        require(not (KIT / 'private' / name).exists(), 'NOT_PRECHECK_ONLY_FAILURE')
    require(not (KIT / 'deployment-status.json').exists(), 'DEPLOYMENT_STATUS_EXISTS')
    require(not (BASE / 'docs/audit-final-20261102.md').exists(), 'HANDOVER_ALREADY_EXISTS')
    core.guard_runtime(manifest)


def validate_lock(metadata):
    require(isinstance(metadata, dict), 'INVALID_LOCK_METADATA')
    require(metadata.get('hostname') == socket.gethostname(), 'LOCK_BELONGS_TO_OTHER_HOST')
    pid = metadata.get('pid')
    require(type(pid) is int and 1 < pid <= 2 ** 31 - 1, 'INVALID_LOCK_PID')
    # Go/restic writes RFC3339Nano; Python 3.10 accepts only three or six
    # fractional digits. Normalize precision before parsing, retaining timezone.
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})', str(metadata.get('time', '')))
    require(match is not None, 'INVALID_LOCK_TIME')
    normalized = match[1] + '.' + (match[2] or '').ljust(6, '0')[:6] + ('+00:00' if match[3] == 'Z' else match[3])
    stamp = datetime.fromisoformat(normalized)
    require((datetime.now(timezone.utc) - stamp).total_seconds() >= -60, 'INVALID_LOCK_TIME')
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    except PermissionError:
        raise ResumeError('LOCK_PROCESS_NOT_PROVEN_DEAD')
    else:
        raise ResumeError('LOCK_PROCESS_STILL_EXISTS')
    return {'pid': pid, 'same_host': True, 'process_exists': False, 'time': stamp.isoformat()}


def lock_ids(repo):
    output = repo.call(['--no-lock', 'list', 'locks'], timeout=120)
    rows = output.splitlines()
    require(len(rows) <= 16 and all(re.fullmatch('[0-9a-f]{64}', row.strip()) for row in rows), 'INVALID_LOCK_INVENTORY')
    ids = [row.strip() for row in rows]
    require(len(set(ids)) == len(ids), 'DUPLICATE_LOCK_ID')
    return sorted(ids)


def remove_stale(repo, save):
    """Inspect every lock before the single native non-forced unlock operation."""
    before = lock_ids(repo)
    safe = []
    for index, identifier in enumerate(before):
        metadata = json.loads(repo.call(['--no-lock', 'cat', 'lock', identifier], timeout=120))
        save('lock-' + str(index) + '.json', metadata)
        safe.append(validate_lock(metadata))
    # Refuse a concurrent or inconsistent inventory; never use --remove-all.
    require(lock_ids(repo) == before, 'LOCK_INVENTORY_CHANGED')
    if before:
        print('A zárolás tulajdonosfolyamata már nem létezik ezen a gépen; natív restic unlock indul, kényszerítés nélkül.', flush=True)
        repo.call(['unlock'], timeout=120)
    after = lock_ids(repo)
    require(not after, 'REPOSITORY_STILL_LOCKED')
    return {'ok': True, 'locks_before': len(before), 'locks_after': 0,
            'proven_dead_local_locks': safe, 'native_unlock_attempted': bool(before),
            'force_used': False, 'snapshots_or_data_deleted': False}


def install_diagnostics(module, root):
    """Log activation subprocess failures too, without changing sealed source."""
    log = load('r21_continuation_operation_log', KIT / 'source/scripts/router_operation_log.py')
    log.OPERATIONS.update(('unlock', 'list', 'cat'))
    cls = module.router.RouterRepository
    original = cls.__init__
    def initialize(self, settings, *, run=subprocess.run, cache=None):
        diagnostics = log.OperationLog(root, uuid.uuid4().hex, run=run)
        original(self, settings, run=diagnostics, cache=cache)
    cls.__init__ = initialize
    # The production precheck must share the same local locks as all workers.
    # Later checks inside the already-started transaction keep their original
    # locking context; nested flock acquisitions would conflict with themselves.
    check = cls.check
    core = module.router.core
    def checked(self):
        if (self.settings['router_repository_path'] == '/G/hc-backup/restic/homecontrol'
                and not core.STATE.exists()):
            with ExitStack() as stack:
                core.locked(stack)
                core.idle()
                return check(self)
        return check(self)
    cls.check = checked


def main():
    require(os.geteuid() == 0, 'LOCAL_SUDO_REQUIRED')
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    verify_sidecar()
    module = load('sealed_r21_activation', KIT / 'source/scripts/audit_release/activate.py')
    core = module.router.core
    manifest = core.verify()
    guard(core, manifest)
    private = SIDECAR / 'private'
    core.platform().no_symlinks(private)
    private.mkdir(mode=0o700, exist_ok=True)
    os.chown(private, 0, 0)
    private.chmod(0o700)
    operator = private / 'operator.lock'
    core.platform().no_symlinks(operator)
    with operator.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not (private / 'started.json').exists(), 'CONTINUATION_ALREADY_ATTEMPTED')
        write = core.platform().write_json
        write(private / 'original-error.json', read(KIT / 'private/audit-error.json'))
        write(private / 'started.json', {'release': NAME, 'started_at': datetime.now(timezone.utc).isoformat()})
        install_diagnostics(module, private)
        with ExitStack() as stack:
            core.locked(stack)
            core.idle()
            from router_backup import private_text
            settings = json.loads(private_text(BASE / 'backups/backup_settings.json'))
            require(settings.get('backup_target') == 'router_ftp'
                    and settings.get('router_repository_path') == '/G/hc-backup/restic/homecontrol', 'UNEXPECTED_REPOSITORY')
            with tempfile.TemporaryDirectory(prefix='hc-r21-stale-lock-') as temporary:
                repo = module.router.RouterRepository(settings, cache=Path(temporary))
                repo.prepare()
                proof = remove_stale(repo, lambda name, value: write(private / name, value))
                write(SIDECAR / 'evidence/lock-recovery.json', proof, 0o644)
        print('Az ellenőrzött r21 folytatása indul. A teljes repository-ellenőrzés, r18 előmentés és PG-restore minden átállítás előtt kötelező.', flush=True)
        module.main('activate')
        require(read(KIT / 'deployment-status.json').get('state') == 'deployed_and_audit_handover_complete', 'HANDOVER_NOT_COMPLETE')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try:
        main()
    except BaseException as error:
        code = str(error) if isinstance(error, ResumeError) else type(error).__name__
        if os.geteuid() == 0 and (SIDECAR / 'private').exists():
            try:
                file = SIDECAR / 'private/continuation-error.json'
                fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump({'error_type': type(error).__name__, 'detail': str(error)}, stream)
            except OSError:
                pass
        print('Az r21 folytatás megállt: ' + code + '. Privát napló megőrizve; az indítást ne ismételd vakon.', file=sys.stderr)
        raise SystemExit(1)
