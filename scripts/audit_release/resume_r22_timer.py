"""Continue approved r22 after the exact health-timer race and verified rollback."""
import copy
from contextlib import ExitStack
import ctypes
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import uuid

BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-audit-20261103-r22'
KIT = BASE / 'backups/releases' / NAME
SIDECAR = BASE / 'backups/releases/hc-audit-20261103-r22-continuation-2'
MANIFEST_SHA256 = '96577f442a6457bb42a85a127a0e8b2d1f166848242ed4f724d705354fa1aa8c'
PREVIOUS = BASE / 'backups/releases/hc-audit-20261103-r22-continuation-1'
RUN = 'ed5dfbc3bf664bfaa44ef9d58f6153c8'
ARCHIVE_SHA256 = 'a92a6fe10b97e60e6a8a6c0b30a549a0010a56a8acc66f842e6e72e4e4df7e5f'
sys.dont_write_bytecode = True


class ResumeError(ValueError): pass
def require(value, code):
    if not value: raise ResumeError(code)
def read(path): return json.loads(Path(path).read_text())
def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''): h.update(block)
    return h.hexdigest()
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def verify_sidecar():
    acceptance = read(SIDECAR / 'acceptance.json')
    require(acceptance.get('ok') is True, 'CONTINUATION_NOT_ACCEPTED')
    for name, expected in acceptance['sha256'].items():
        path = SIDECAR / name
        require(not any(p.is_symlink() for p in (path, *path.parents)) and digest(path) == expected, 'CONTINUATION_CHANGED')
    require(digest(KIT / 'release.json') == MANIFEST_SHA256, 'R22_MANIFEST_CHANGED')


def rebase_manifest(core, manifest):
    """Adopt only the three verified r18 container IDs recreated by rollback."""
    result = copy.deepcopy(manifest)
    changed = {core.container(n) for n in manifest['changed_services']}
    require(changed == {'homecontrol-backend', 'homecontrol-mdns', 'homecontrol-ha-growatt-poller'}, 'UNEXPECTED_CHANGED_COMPONENTS')
    for name, before in manifest['baseline'].items():
        row = json.loads(core.call(['docker', 'inspect', name]).stdout)[0]
        require(row['Image'] == before['image'], 'R18_IMAGE_CHANGED')
        require(re.fullmatch('[0-9a-f]{64}', row['Id']) is not None, 'INVALID_CONTAINER_ID')
        require(name == 'homecontrol-adminer' or row['State']['Running'], 'R18_COMPONENT_STOPPED')
        require(not row['State']['Running'] or row['State'].get('Health', {}).get('Status') in (None, 'healthy'), 'R18_COMPONENT_UNHEALTHY')
        if name in changed: result['baseline'][name]['id'] = row['Id']
        else: require(row['Id'] == before['id'], 'UNCHANGED_R18_CONTAINER_REPLACED')
    core.guard_runtime(result)
    return result


def guard_old_units(core):
    prior = read(BASE / 'backups/releases' / core.OLD / 'release.json')
    for name, expected in prior['source_sha256'].items():
        require(digest(core.OLD_RUNTIME / name) == expected, 'R18_RUNTIME_CHANGED')
    common = load('verified_previous_release_units', core.OLD_RUNTIME / 'scripts/access_release/common.py')
    for name, text in common.units(core.OLD_RUNTIME, runtime=core.OLD_RUNTIME).items():
        path = core.UNIT_ROOT / name; core.platform().no_symlinks(path)
        require(digest(path) == hashlib.sha256(text.encode()).hexdigest(), 'R18_ACCESS_UNIT_CHANGED')


def guard(core, manifest):
    require(read(KIT / 'deployment-status.json').get('phase') == 'previous_release_restored', 'ROLLBACK_NOT_COMPLETE')
    require(read(core.STATE / 'result.json') == {'state': 'rolled_back', 'success': True}, 'ROLLBACK_RESULT_CHANGED')
    require(read(core.STATE / 'transition.json').get('release') == NAME, 'TRANSITION_RELEASE_CHANGED')
    error = read(PREVIOUS / 'private/continuation-error.json')
    require(error == {'error_type': 'ValueError', 'detail': 'Scheduled timer has no next trigger: homecontrol-post-boot-health.timer'}, 'UNEXPECTED_HANDOVER_ERROR')
    require(not (BASE / 'docs/audit-final-20261102.md').exists()
            and not (KIT / 'evidence/post-live-check.json').exists(), 'HANDOVER_ALREADY_EXISTS')
    proof = read(KIT / 'evidence/router-live-acceptance.json')
    require(proof.get('ok') is True and proof.get('release') == NAME and proof.get('run_id') == RUN
            and proof.get('snapshot_id') == 'e13b233aefaeb74e4be4878acb576765d1cec77a1dbac7d6f67a6ab2239fa00b'
            and proof.get('restore') == 'verified' and proof.get('database') == 'verified'
            and proof.get('git') == 'pushed' and proof.get('ai_enabled') is False, 'PRIOR_RESTORE_PROOF_CHANGED')
    job = read(BASE / 'backups/backup-state.json')
    require(job.get('run_id') == RUN and job.get('state') == 'completed' and job.get('returncode') == 0
            and job.get('archive', {}).get('sha256') == ARCHIVE_SHA256, 'COMPLETED_R22_RUN_CHANGED')
    for name in ('local_archive', 'restic', 'git_offsite', 'secrets_bundle', 'restic_retention'):
        require(job.get('targets', {}).get(name, {}).get('state') == 'succeeded', 'PRIOR_BACKUP_TARGET_CHANGED')
    require(job == read(BASE / 'backups/runs' / (RUN + '.json')), 'PRIOR_RUN_RECEIPT_CHANGED')
    for path in (core.RUNTIME, core.PRIVATE, KIT / 'private/baseline-runner'):
        require(path.is_dir() and not path.is_symlink(), 'FAILED_INSTALL_DIRECTORY_MISSING')
    actual = {}
    for path in core.RUNTIME.rglob('*'):
        core.platform().no_symlinks(path)
        require(path.is_dir() or path.is_file(), 'SPECIAL_FAILED_RUNTIME_ENTRY')
        if path.is_file() and '__pycache__' not in path.parts: actual[str(path.relative_to(core.RUNTIME))] = digest(path)
    require(actual == manifest['source_sha256'], 'FAILED_RUNTIME_CHANGED')
    require(read(core.PRIVATE / 'installed.json') == {'release': NAME, 'state': 'running_requires_supervised_acceptance',
            'transition': str(core.STATE)}, 'PREVIOUS_INSTALL_RECEIPT_CHANGED')
    expected, actual = {}, {}
    for root, found in ((KIT / 'private/runtime', expected), (core.PRIVATE, actual)):
        for path in root.rglob('*'):
            core.platform().no_symlinks(path)
            require(path.is_dir() or path.is_file(), 'SPECIAL_FAILED_PRIVATE_ENTRY')
            if path.is_file():
                relative = str(path.relative_to(root))
                if root == core.PRIVATE and relative == 'installed.json': continue
                found[relative] = digest(path)
    require(actual == expected and actual, 'FAILED_PRIVATE_TREE_CHANGED')
    require(not core.active('homecontrol-r22-acceptance-backup.service'), 'SUPERVISOR_STILL_ACTIVE')
    guard_old_units(core)
    core.guard_runtime(manifest)
    return error


def exclusive_rename(source, target):
    # Atomically refuse an existing archive destination, including empty dirs.
    function = ctypes.CDLL(None, use_errno=True).renameat2
    function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    if function(-100, os.fsencode(source), -100, os.fsencode(target), 1):
        number = ctypes.get_errno(); raise OSError(number, os.strerror(number))


def preserve_failed_install(core, token):
    paths = [core.RUNTIME, core.PRIVATE, core.STATE, KIT / 'private/baseline-runner']
    moves = [(path, path.with_name(path.name + '-preserved-' + token)) for path in paths]
    for before, after in moves:
        core.platform().no_symlinks(before); core.platform().no_symlinks(after)
        require(before.is_dir() and not after.exists(), 'PRESERVATION_DESTINATION_EXISTS')
    completed = []
    try:
        for before, after in moves:
            exclusive_rename(before, after); completed.append((before, after))
    except BaseException:
        for before, after in reversed(completed): exclusive_rename(after, before)
        raise
    return [{'original': str(before), 'preserved': str(after)} for before, after in moves]


def main():
    require(os.geteuid() == 0, 'LOCAL_SUDO_REQUIRED')
    os.umask(0o077); os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    verify_sidecar()
    module = load('sealed_r22_install_continuation', KIT / 'source/scripts/audit_release/activate.py')
    core = module.router.core; original_manifest = core.verify()
    manifest = rebase_manifest(core, original_manifest)
    error = guard(core, manifest)
    original_load = core.load
    def adopted_load():
        require(original_load() == original_manifest, 'R22_MANIFEST_CHANGED_DURING_CONTINUATION')
        return copy.deepcopy(manifest)
    core.load = adopted_load
    private = SIDECAR / 'private'
    core.platform().no_symlinks(private); private.mkdir(exist_ok=True, mode=0o700)
    os.chown(private, 0, 0); private.chmod(0o700)
    operator = private / 'operator.lock'; core.platform().no_symlinks(operator)
    with operator.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not (private / 'started.json').exists(), 'CONTINUATION_ALREADY_ATTEMPTED')
        write = core.platform().write_json
        write(private / 'original-error.json', error)
        write(private / 'adopted-baseline.json', {'original': original_manifest['baseline'], 'current': manifest['baseline'], 'only_three_changed_service_ids_adopted': True})
        for name in ('router-live-acceptance.json', 'baseline-backup-restore.json', 'platform-live.json'):
            write(private / ('prior-' + name), read(KIT / 'evidence' / name))
        write(private / 'started.json', {'release': NAME, 'started_at': datetime.now(timezone.utc).isoformat()})
        core.call(['python3', '/usr/local/lib/homecontrol-backup-storage/migrate.py', 'check'])
        staging = load('r22_verified_staging_guard', SIDECAR / 'source/staging_guard.py')
        staging.BASE = BASE; staging.NAME = NAME; staging.KIT = KIT; staging.SIDECAR = SIDECAR
        adapter = load('r22_verified_diagnostic_adapter', SIDECAR / 'source/diagnostic_adapter.py')
        adapter.KIT = KIT; adapter.install_diagnostics(module, private)
        with ExitStack() as stack:
            core.locked(stack); core.idle(); guard(core, manifest)
            staging.staged_private(core, manifest)
            settings = json.loads(module.router.private_text(BASE / 'backups/backup_settings.json'))
            require(settings.get('backup_target') == 'router_ftp'
                    and settings.get('router_repository_path') == '/G/hc-backup/restic/homecontrol', 'UNEXPECTED_REPOSITORY')
            with tempfile.TemporaryDirectory(prefix='hc-r22-timer-lock-') as temporary:
                repo = module.router.RouterRepository(settings, cache=Path(temporary)); repo.prepare()
                require(not adapter.lock_ids(repo), 'NEW_REPOSITORY_LOCK_NO_UNLOCK_REPEATED')
            # Reuse the verified private staging; preserve all failed destinations
            # and the completed shadow runner without deleting their contents.
            token = uuid.uuid4().hex[:12]
            write(private / 'preservation-intent.json', {'token': token, 'paths': [str(p) for p in
                  (core.RUNTIME, core.PRIVATE, core.STATE, KIT / 'private/baseline-runner')]})
            moves = preserve_failed_install(core, token)
            write(private / 'preserved-paths.json', moves)
        core.prepare_private = lambda m: staging.staged_private(core, m)
        sys.path.insert(0, str(KIT / 'source/scripts/audit_release'))
        import image_cache
        require(Path(image_cache.__file__).resolve() == KIT / 'source/scripts/audit_release/image_cache.py', 'UNEXPECTED_CACHE_MODULE')
        transfer = load('sealed_r22_cache_transfer', SIDECAR / 'source/cache_transfer.py')
        def link(source, target, expected_sha256, *, uid=0):
            proof = transfer.transfer_archive(source, target, expected_sha256, uid=uid)
            write(SIDECAR / 'evidence/cache-transfer.json', {'ok': True, **proof}, 0o644)
        image_cache.link_archive = link
        import schedules
        require(Path(schedules.__file__).resolve() == KIT / 'source/scripts/audit_release/schedules.py', 'UNEXPECTED_SCHEDULE_MODULE')
        settle = load('sealed_r22_timer_settle', SIDECAR / 'source/timer_settle.py')
        settle.install(core, schedules)
        print('Az r22 pontos timer-záróhibája és az r18 rollback ellenőrzött. Új teljes előmentés/restore után folytatódik az engedélyezett r22 élesítése; a záróellenőrzés megvárja a health futás sikeres végét és az új időpontot.', flush=True)
        module.main('activate')
        require(read(KIT / 'deployment-status.json').get('state') == 'deployed_and_audit_handover_complete', 'HANDOVER_NOT_COMPLETE')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try: main()
    except BaseException as error:
        if os.geteuid() == 0:
            try:
                fd = os.open(SIDECAR / 'private/continuation-error.json', os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream: json.dump({'error_type': type(error).__name__, 'detail': str(error)}, stream)
            except OSError: pass
        code = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_]+', str(error)) else type(error).__name__
        print('Az r22 folytatás megállt: ' + code + '. Privát napló megőrizve; ne ismételd vakon.', file=sys.stderr)
        raise SystemExit(1)
