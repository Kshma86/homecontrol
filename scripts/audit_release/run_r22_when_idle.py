"""Log early guards and wait for docking before the approved, sealed r22 entrypoint."""
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid

BASE = Path('/srv/docker/homecontrol')
SIDECAR = BASE / 'backups/releases/hc-audit-20261103-r22-continuation-2'
ENTRY = SIDECAR / 'source/resume_r22_timer.py'
ENTRY_SHA256 = 'd29bca87303094a318cea1bf3d8bebb48df134d41034d7c4aa6cd10412c72147'
ROBOT_GATE = 'Robot must be idle or charging for the bridge handover'
SAFE_ERRORS = {
    ROBOT_GATE, 'Robot idle wait timed out', 'Continuation has already started',
    'Pinned image missing', 'Offline image archive changed', 'Acceptance report changed',
    'Acceptance failed', 'Release acceptance is incomplete', 'Wrong release',
    'Active Compose changed', 'Existing backend is not ready', 'Active irrigation session',
    'Existing hostops/MQTT guard is not active', 'Active backup/restore operation',
    'Active host job; reconcile first', 'Entry script changed',
}
sys.dont_write_bytecode = True


def require_unstarted(private):
    if (private / 'started.json').exists():
        raise ValueError('Continuation has already started')


def wait_for_robot(ready, *, timeout=7200, clock=time.monotonic, sleep=time.sleep, report=print):
    deadline = clock() + timeout
    while True:
        try:
            return ready()
        except ValueError as error:
            # Do not retry any other guard, including a subclass with a different
            # meaning. This never sends a command to the robot.
            if type(error) is not ValueError or str(error) != ROBOT_GATE: raise
        if clock() >= deadline: raise ValueError('Robot idle wait timed out')
        report('A robot még nem dokkolt/tölt; csak olvasó várakozás, az élesítés nem indult el.', flush=True)
        sleep(min(30, deadline - clock()))


def protected_directory(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Unsafe diagnostic directory')
    path.mkdir(mode=0o700, exist_ok=True)
    os.chown(path, 0, 0); path.chmod(0o700)


def save_error(path, phase, error):
    # Exclusive files preserve every attempt, including failures before the
    # original entrypoint creates its own started.json and error receipt.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    frames = []; trace = error.__traceback__
    while trace:
        source = Path(trace.tb_frame.f_code.co_filename)
        try: relative = str(source.relative_to(BASE))
        except ValueError: relative = 'external_module'
        frames.append({'source': relative, 'line': trace.tb_lineno,
                       'function': trace.tb_frame.f_code.co_name})
        trace = trace.tb_next
    with os.fdopen(fd, 'w') as stream:
        json.dump({'checked_at': datetime.now(timezone.utc).isoformat(), 'phase': phase,
                   'error_type': type(error).__name__, 'detail': str(error), 'frames': frames}, stream)
        stream.flush(); os.fsync(stream.fileno())


def main():
    if os.geteuid() != 0: raise PermissionError('Local sudo is required')
    os.umask(0o077); os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    if any(p.is_symlink() for p in (ENTRY, *ENTRY.parents)) or hashlib.sha256(ENTRY.read_bytes()).hexdigest() != ENTRY_SHA256:
        raise ValueError('Entry script changed')
    private = SIDECAR / 'private'
    protected_directory(private)
    log = private / ('early-error-' + uuid.uuid4().hex + '.json')
    phase = 'load_verified_entry'; resume = None
    try:
        lock = private / 'early-operator.lock'
        if lock.is_symlink(): raise ValueError('Unsafe diagnostic lock')
        with lock.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require_unstarted(private)
            spec = importlib.util.spec_from_file_location('sealed_r22_timer_operator', ENTRY)
            resume = importlib.util.module_from_spec(spec); spec.loader.exec_module(resume)
            phase = 'verify_sidecar'; resume.verify_sidecar()
            activation = resume.load('readonly_r22_early_guards', resume.KIT / 'source/scripts/audit_release/activate.py')
            core = activation.router.core
            phase = 'verify_release'; manifest = core.verify()
            phase = 'wait_robot_idle'
            wait_for_robot(lambda: resume.rebase_manifest(core, manifest))
            require_unstarted(private)
            phase = 'activate_r22'
            print('A korai kapuk teljesülnek. A változatlan, ellenőrzött r22 folytató indul; minden mentési és restore-kapu kötelező.', flush=True)
            resume.main()
    except BaseException as error:
        save_error(log, phase, error)
        condition = str(error) if str(error) in SAFE_ERRORS else type(error).__name__
        if resume is not None and isinstance(error, resume.ResumeError): condition = str(error)
        print('r22 megállt; fázis: ' + phase + '; ok: ' + condition + '. Privát napló: ' + str(log), file=sys.stderr)
        raise


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try: main()
    except BaseException:
        # Full details stay in the root-only receipt, never in the terminal.
        raise SystemExit(1)
