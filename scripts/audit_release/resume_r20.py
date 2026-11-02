"""Guarded continuation of the specific r20 pre-cutover backup timeout."""
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile

BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-audit-20261102-r20'
KIT = BASE / 'backups/releases' / NAME
SIDECAR = BASE / 'backups/releases/hc-audit-20261102-r20-continuation-1'
MANIFEST_SHA256 = '873f9f9cb75ef7a63de2fb3c74378ccb0c49dddd01ba6b071ced7cd668492a02'
RUN = '1931f52994584f34b178e8e7a192bb2d'
ARCHIVE = 'homecontrol_2026-11-02_21-18-26_' + RUN + '.tar.gz'
ARCHIVE_SHA256 = 'c0a445b33b02e993798a7037a7030d3136b2ee5a90ca6190861fb8f1a2eff00d'
MAX_AGE_SECONDS = 4 * 3600
sys.dont_write_bytecode = True


class ResumeError(ValueError):
    pass


def require(value, code):
    if not value:
        raise ResumeError(code)


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(data)
    return h.hexdigest()


def verify_sidecar():
    receipt = read(SIDECAR / 'acceptance.json')
    require(receipt.get('ok') is True, 'CONTINUATION_NOT_ACCEPTED')
    for name, expected in receipt['sha256'].items():
        path = SIDECAR / name
        require(not path.is_symlink() and digest(path) == expected, 'CONTINUATION_CHANGED')
    require(digest(KIT / 'release.json') == MANIFEST_SHA256, 'R20_MANIFEST_CHANGED')


def activation():
    spec = importlib.util.spec_from_file_location('sealed_r20_activation', KIT / 'source/scripts/audit_release/activate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard(core, manifest):
    require(read(KIT / 'deployment-status.json').get('phase') == 'fresh_backup', 'NOT_PRE_CUTOVER_TIMEOUT')
    error = read(KIT / 'private/audit-error.json')
    command = ['python3', str(core.OLD_RUNTIME / 'scripts/hostops/backup_runner.py'), '--mode', 'local']
    require(error == {'error_type': 'TimeoutExpired', 'detail': str(subprocess.TimeoutExpired(command, 900))}, 'UNEXPECTED_ORIGINAL_ERROR')
    require(not core.STATE.exists(), 'TRANSITION_ALREADY_EXISTS')
    require(not core.RUNTIME.exists() and not core.PRIVATE.exists(), 'CUTOVER_ALREADY_STARTED')
    require(not (BASE / 'docs/audit-final-20261102.md').exists(), 'HANDOVER_ALREADY_EXISTS')
    core.guard_runtime(manifest)
    return read(KIT / 'private/progress.json')


def archive_receipt():
    receipt = read(BASE / 'backups' / (ARCHIVE + '.complete.json'))
    require(receipt.get('completed') is True and receipt.get('run_id') == RUN
            and receipt.get('name') == ARCHIVE and receipt.get('mode') == 'local'
            and receipt.get('sha256') == ARCHIVE_SHA256, 'PRE_BACKUP_RECEIPT_MISMATCH')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(receipt['timestamp'])).total_seconds()
    require(0 <= age <= MAX_AGE_SECONDS, 'PRE_BACKUP_OLDER_THAN_FOUR_HOURS')
    coverage = receipt.get('coverage', {})
    require(all(coverage.get('include_' + n) is True for n in
                ('postgres', 'apps', 'infra', 'zigbee2mqtt', 'homeassistant', 'scripts', 'docker_meta')),
            'PRE_BACKUP_COVERAGE_INCOMPLETE')
    return receipt


def recover_job(core):
    """Record the dead runner as interrupted; never invent successful completion."""
    with ExitStack() as stack:
        core.locked(stack)
        core.idle()
        path = BASE / 'backups/runs' / (RUN + '.json')
        job = read(path)
        state = read(BASE / 'backups/backup-state.json')
        require(state == job and job.get('run_id') == RUN and job.get('state') == 'running', 'BACKUP_STATE_CHANGED')
        require(job.get('mode') == 'local' and job.get('scope') == 'router', 'BACKUP_SCOPE_CHANGED')
        pid = job.get('pid')
        require(isinstance(pid, int) and pid > 1, 'INVALID_RUNNER_PID')
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise ResumeError('RUNNER_PID_STILL_EXISTS')
        receipt = archive_receipt()
        require(job.get('archive') == receipt, 'RUNNER_ARCHIVE_CHANGED')
        core.platform().write_json(SIDECAR / 'private/interrupted-run-original.json', job)
        job.update(state='failed', finished_at=datetime.now(timezone.utc).isoformat(), returncode=124,
                   error='Activation caller timed out at 900 seconds; interrupted runner reconciled under both locks',
                   reconciliation='r20-continuation-1', local_archive_preserved=True)
        core.platform().write_json(path, job, 0o644)
        core.platform().write_json(BASE / 'backups/backup-state.json', job, 0o644)


def staged_private(core, manifest):
    """Compare existing private staging with the current old inputs and encrypted bundle."""
    root = KIT / 'private/runtime'
    expected = {}
    for name in ('compose-env', 'mqtt'):
        require((core.OLD_PRIVATE / name).is_dir() and (root / name).is_dir(), 'STAGED_PRIVATE_DIRECTORY_MISSING')
        for path in (core.OLD_PRIVATE / name).rglob('*'):
            core.platform().no_symlinks(path)
            if path.is_file():
                relative = path.relative_to(core.OLD_PRIVATE)
                data = path.read_bytes()
                if name == 'compose-env' and path.parent == core.OLD_PRIVATE / name and path.suffix == '.env':
                    data = data.replace(str(core.OLD_RUNTIME).encode(), str(core.RUNTIME).encode()).replace(str(core.OLD_PRIVATE).encode(), str(core.PRIVATE).encode())
                expected[str(relative)] = hashlib.sha256(data).hexdigest()
    core.platform().no_symlinks(core.OLD_PRIVATE / 'network-policy.json')
    expected['network-policy.json'] = digest(core.OLD_PRIVATE / 'network-policy.json')
    actual = {}
    for path in root.rglob('*'):
        core.platform().no_symlinks(path)
        require(path.is_dir() or path.is_file(), 'STAGED_SPECIAL_FILE')
        if path.is_file() and not path.is_relative_to(root / 'images'):
            actual[str(path.relative_to(root))] = digest(path)
    require(expected == actual and expected, 'STAGED_PRIVATE_INPUTS_CHANGED')
    policy = read(root / 'network-policy.json')
    require(policy.get('esp_ip') == '192.168.1.179' and policy.get('esp_confirmed') is True, 'ESP_POLICY_CHANGED')
    require({p.name for p in (root / 'images').iterdir()} == {'access-images.tar.gz', 'manifest.json'}, 'STAGED_IMAGE_CACHE_CHANGED')
    require(digest(root / 'images/access-images.tar.gz') == manifest['offline_image_archive_sha256'], 'STAGED_IMAGES_CHANGED')
    require(read(root / 'images/manifest.json') == {'archive': 'access-images.tar.gz', 'sha256': manifest['offline_image_archive_sha256'], 'images': manifest['recovery_images']}, 'STAGED_IMAGE_MANIFEST_CHANGED')
    encrypted = KIT / 'private/homecontrol-secrets-r13.tar.gz.age'
    receipt = read(KIT / 'private/secret-receipt.json')
    require(receipt.get('roundtrip_verified') is True and receipt.get('sha256') == digest(encrypted), 'SECRET_RECEIPT_CHANGED')
    sys.path.insert(0, str(KIT / 'source/scripts'))
    from restore_archive import secrets
    with tempfile.TemporaryDirectory(prefix='.resume-r20-', dir=SIDECAR / 'private') as folder:
        work = Path(folder)
        packed = work / 'bundle.tar.gz'
        packed.write_bytes(core.call(['age', '-d', '-i', str(BASE / 'infra/ssh/homecontrol-secrets-age-key.txt'), str(encrypted)]).stdout)
        packed.chmod(0o600)
        decoded = work / 'root'
        secrets(packed, decoded)
        require((decoded / 'SECRETS_BUNDLE_METADATA.txt').read_text() == 'release=' + NAME + '\n', 'ENCRYPTED_RELEASE_CHANGED')
        files = [p for p in decoded.rglob('*') if p.is_file() and not p.name.startswith('SECRETS_BUNDLE_')]
        require(len(files) == receipt['files'], 'ENCRYPTED_FILE_COUNT_CHANGED')
        for relative, expected_hash in expected.items():
            require(digest(decoded / str(core.PRIVATE).lstrip('/') / relative) == expected_hash, 'ENCRYPTED_STAGING_MISMATCH')
    core.platform().write_json(SIDECAR / 'private/staging-reverified.json', {'ok': True, 'files': len(expected), 'encrypted_roundtrip': True})


def reuse_pre_backup(core):
    with ExitStack() as stack:
        core.locked(stack)
        receipt = archive_receipt()
        path = BASE / 'backups' / ARCHIVE
        core.platform().no_symlinks(path)
        sys.path.insert(0, str(KIT / 'source/infra/backend'))
        from backup_protocol import verify_archive
        print('Az eredeti aktiválás friss helyi mentésének teljes SHA-256/tartalom-visszaellenőrzése.', flush=True)
        checked = verify_archive(path)
        require(checked['sha256'] == ARCHIVE_SHA256 and checked['size_bytes'] == receipt['size_bytes']
                and checked['verified_files'] == receipt['verified_files'], 'PRE_BACKUP_CONTENT_CHANGED')
        core.platform().write_json(KIT / 'private/pre-backup.json', {
            'name': ARCHIVE, **checked, 'run_id': RUN, 'continuation': 'same activation; published before 900 s caller timeout',
            'original_job_state': 'interrupted; not treated as a completed router job'})


def main():
    require(os.geteuid() == 0, 'LOCAL_SUDO_REQUIRED')
    verify_sidecar()
    module = activation()
    core = module.router.core
    manifest = core.verify()
    guard(core, manifest)
    archive = archive_receipt()
    # Budget one installed image cache, one new weekly archive and 2 GiB reserve.
    required = (KIT / 'private/access-images.tar.gz').stat().st_size + archive['size_bytes'] + 2 * 1024 ** 3
    require(shutil.disk_usage(BASE).free >= required, 'INSUFFICIENT_CUTOVER_SPACE')
    private = SIDECAR / 'private'
    core.platform().no_symlinks(private)
    private.mkdir(mode=0o700, exist_ok=True)
    os.chown(private, 0, 0)
    private.chmod(0o700)
    with (private / 'operator.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not (private / 'started.json').exists(), 'CONTINUATION_ALREADY_ATTEMPTED')
        core.platform().write_json(private / 'original-error.json', read(KIT / 'private/audit-error.json'))
        core.platform().write_json(private / 'started.json', {'release': NAME, 'run_id': RUN, 'started_at': datetime.now(timezone.utc).isoformat()})
        def prepare(m):
            staged_private(core, m)
            recover_job(core)
        core.prepare_private = prepare
        core.fresh_backup = lambda: reuse_pre_backup(core)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from backup_supervision import install
        install(core)
        print('Az r20 átállítás előtti, ellenőrzött folytatása indul; új alkalmazáscsomag nem készül.', flush=True)
        module.main('activate')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try:
        main()
    except BaseException as error:
        code = str(error) if isinstance(error, ResumeError) else type(error).__name__
        if os.geteuid() == 0 and (SIDECAR / 'private').exists():
            try:
                (SIDECAR / 'private/continuation-error.json').write_text(json.dumps({'error_type': type(error).__name__, 'detail': str(error)}))
                (SIDECAR / 'private/continuation-error.json').chmod(0o600)
            except OSError:
                pass
        print('Az r20 folytatás megállt: ' + code + '. Az aktiválást ne ismételd vakon.', file=sys.stderr)
        raise SystemExit(1)
