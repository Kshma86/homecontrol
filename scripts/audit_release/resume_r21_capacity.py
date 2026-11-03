"""Continue r21 after its verified lock recovery and capacity-only stop."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys

BASE = Path('/srv/docker/homecontrol')
PRIOR = BASE / 'backups/releases/hc-audit-20261102-r21-continuation-1'
SIDECAR = BASE / 'backups/releases/hc-audit-20261102-r21-continuation-2'
PRIOR_ACCEPTANCE_SHA256 = '06908e227a9edab3be3d536736c612ebd01fb81ce974a27a90b07113a206ba14'
PRIOR_LOCK_PROOF_SHA256 = 'c8b8d33d74c1eb5ba6cad8674fdd19917cf4c48040a430808afc3fa1ffd43e30'
CAPACITY_ERROR = {'error_type': 'ValueError', 'detail': 'Insufficient space for pre/post backups plus 2 GiB reserve'}
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
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 ** 2), b''): result.update(data)
    return result.hexdigest()


def verify_package(root):
    receipt = read(root / 'acceptance.json')
    require(receipt.get('ok') is True, 'CONTINUATION_NOT_ACCEPTED')
    for name, expected in receipt['sha256'].items():
        path = root / name
        require(not path.is_symlink() and digest(path) == expected, 'CONTINUATION_CHANGED')


def guard_previous():
    require(digest(PRIOR / 'acceptance.json') == PRIOR_ACCEPTANCE_SHA256, 'PRIOR_ACCEPTANCE_CHANGED')
    verify_package(PRIOR)
    require(digest(PRIOR / 'evidence/lock-recovery.json') == PRIOR_LOCK_PROOF_SHA256, 'LOCK_RECOVERY_PROOF_CHANGED')
    proof = read(PRIOR / 'evidence/lock-recovery.json')
    require(proof.get('ok') is True and proof.get('locks_after') == 0 and proof.get('force_used') is False, 'LOCK_RECOVERY_NOT_VERIFIED')
    require(read(PRIOR / 'private/continuation-error.json') == CAPACITY_ERROR, 'PRIOR_FAILURE_IS_NOT_CAPACITY_ONLY')


def capacity():
    sizes = []
    for path in (BASE / 'backups').glob('homecontrol_*.tar.gz.complete.json'):
        receipt = read(path)
        if receipt.get('completed') is True:
            size = receipt.get('size_bytes')
            require(type(size) is int and size > 0, 'INVALID_ARCHIVE_SIZE')
            sizes.append(size)
    required = 2 * max(sizes or [3 * 1024 ** 3]) + 2 * 1024 ** 3
    free = shutil.disk_usage(BASE).free
    print('Tárhely: szabad {} bájt; szükséges {} bájt (két mentés és 2 GiB tartalék).'.format(free, required), flush=True)
    require(free >= required, 'INSUFFICIENT_SPACE_FREE_{}_REQUIRED_{}'.format(free, required))
    return {'ok': True, 'free_bytes': free, 'required_bytes': required, 'reserve_bytes': 2 * 1024 ** 3, 'original_threshold_preserved': True}


def ensure_unlocked(adapter, repo):
    require(not adapter.lock_ids(repo), 'NEW_REPOSITORY_LOCK_EXISTS_NO_UNLOCK_REPEATED')
    return {'ok': True, 'locks_before': 0, 'locks_after': 0, 'native_unlock_attempted': False,
            'previous_recovery_verified': True, 'force_used': False, 'snapshots_or_data_deleted': False}


def main():
    require(os.geteuid() == 0, 'LOCAL_SUDO_REQUIRED')
    verify_package(SIDECAR)
    guard_previous()
    proof = capacity()
    spec = importlib.util.spec_from_file_location('verified_r21_continuation_adapter', PRIOR / 'source/resume_r21.py')
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    # Reuse the sealed and tested guards, diagnostics, common lock adapter and
    # full activation. A fresh receipt namespace preserves the previous failure.
    adapter.SIDECAR = SIDECAR
    adapter.remove_stale = lambda repo, save: ensure_unlocked(adapter, repo)
    guard = adapter.guard
    def checked(core, manifest):
        guard(core, manifest)
        core.platform().write_json(SIDECAR / 'evidence/capacity-before.json', proof, 0o644)
    adapter.guard = checked
    print('A korábbi lock-feloldás ellenőrzött; azt nem ismételjük. A tárhelykapu teljesül, az r21 ellenőrzött folytatása indul.', flush=True)
    adapter.main()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try:
        main()
    except BaseException as error:
        detail = str(error)
        code = detail if re.fullmatch('[A-Z0-9_]+', detail) else type(error).__name__
        if os.geteuid() == 0:
            try:
                private = SIDECAR / 'private'
                private.mkdir(mode=0o700, exist_ok=True)
                file = private / 'capacity-continuation-error.json'
                fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump({'error_type': type(error).__name__, 'detail': detail,
                               'timestamp': datetime.now(timezone.utc).isoformat()}, stream)
            except OSError:
                pass
        print('Az r21 folytatás megállt: ' + code + '. A privát napló megőrizve.', file=sys.stderr)
        raise SystemExit(1)
