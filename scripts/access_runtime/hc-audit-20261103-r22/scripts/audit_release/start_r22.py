"""Start the new r22 release only from the recorded r21 baseline transport stop."""
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
import sys
import tempfile

BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-audit-20261103-r22'
KIT = BASE / 'backups/releases' / NAME
PRIOR = BASE / 'backups/releases/hc-audit-20261102-r21'
PREVIOUS_CONTINUATION = BASE / 'backups/releases/hc-audit-20261102-r21-continuation-2'
PRIOR_MANIFEST = 'd31eb653cafbaf8f3514e6e96690b013a3fd2410a5a70c28fece012593489f20'
RUN = '37e3acdd8a374fc4a2a48422ab830ed5'
ARCHIVE_SHA = '894acb8a7e64313dbfd0c950f233ca9b4c836d48df6f13afc0e1b7f0a6004956'
sys.dont_write_bytecode = True


class StartError(ValueError): pass
def require(value, code):
    if not value: raise StartError(code)
def read(path): return json.loads(Path(path).read_text())
def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''): h.update(block)
    return h.hexdigest()
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def guard_state(core, manifest):
    require(digest(PRIOR / 'release.json') == PRIOR_MANIFEST, 'PRIOR_MANIFEST_CHANGED')
    old = read(PRIOR / 'release.json')
    require(len(old['source_sha256']) == 799 and all(digest(PRIOR / 'source' / name) == expected
            for name, expected in old['source_sha256'].items()), 'PRIOR_SOURCE_CHANGED')
    require(read(PRIOR / 'deployment-status.json').get('phase') == 'baseline_full_backup', 'PRIOR_PHASE_CHANGED')
    for path in (core.STATE, core.RUNTIME, core.PRIVATE, PRIOR / 'private/transition',
                 BASE / 'scripts/access_runtime/hc-audit-20261102-r21', BASE / 'infra/ssh/hc-audit-20261102-r21',
                 BASE / 'docs/audit-final-20261102.md'):
        require(not path.exists(), 'CUTOVER_OR_HANDOVER_ALREADY_EXISTS')
    job = read(BASE / 'backups/backup-state.json')
    require(job.get('run_id') == RUN and job.get('state') == 'failed' and job.get('mode') == 'weekly'
            and job.get('scope') == 'router', 'FAILED_RUN_CHANGED')
    require(job == read(BASE / 'backups/runs' / (RUN + '.json')), 'RUN_RECEIPT_CHANGED')
    for name in ('local_archive', 'secrets_bundle', 'git_offsite'):
        require(job.get('targets', {}).get(name, {}).get('state') == 'succeeded', 'FAILED_RUN_SCOPE_CHANGED')
    require(job.get('targets', {}).get('restic', {}).get('state') == 'failed'
            and job['targets']['restic'].get('detail') == 'Router snapshot failed; local archive retained; restic backup exit 1',
            'ORIGINAL_FAILURE_CHANGED')
    require(job.get('archive', {}).get('completed') is True and job['archive'].get('sha256') == ARCHIVE_SHA,
            'ORIGINAL_ARCHIVE_RECEIPT_CHANGED')
    pid = job.get('pid')
    require(type(pid) is int and pid > 1, 'INVALID_FAILED_RUN_PID')
    try: os.kill(pid, 0)
    except ProcessLookupError: pass
    else: raise StartError('FAILED_RUN_PID_STILL_EXISTS')
    core.guard_runtime(manifest)
    require(not core.active('homecontrol-r21-acceptance-backup.service'), 'OLD_SUPERVISOR_STILL_ACTIVE')
    return job


def guard_failure(diag):
    error = diag.read_private(PREVIOUS_CONTINUATION / 'private/capacity-continuation-error.json')
    require(error.get('error_type') == 'RuntimeError' and error.get('detail') == 'Release operation failed: systemd-run',
            'UNEXPECTED_CONTINUATION_ERROR')
    logs = [p for p in (BASE / 'backups/router-diagnostics').glob(RUN + '-*.json')
            if re.fullmatch(RUN + r'-[0-9a-f]{32}\.json', p.name)]
    require(len(logs) == 1, 'ORIGINAL_DIAGNOSTIC_SET_CHANGED')
    payload = diag.read_private(logs[0])
    require(payload.get('run_id') == RUN and payload.get('tool') == 'restic' and payload.get('operation') == 'backup'
            and payload.get('exit_code') == 1 and payload.get('stderr_truncated') is False, 'ORIGINAL_DIAGNOSTIC_CHANGED')
    proof = diag.summary(payload)
    require(set(proof['error_classes']) == {'transport', 'backend_write'}, 'UNEXPECTED_ERROR_CLASS')
    groups = proof['stderr_groups']
    require(any('tcp_write_timeout' in row['conditions'] and 'ftp_control_port_21' in row['tcp_peer_roles']
                and 'ftp_create_parent' in row['stages'] for row in groups), 'FTP_CONTROL_WRITE_TIMEOUT_NOT_PROVEN')
    require(any('tcp_write_timeout' in row['conditions'] and 'ftp_control_port_21' in row['tcp_peer_roles']
                and 'restic_bridge_delete' in row['stages'] and 'lock' in row['repository_object_kinds']
                for row in groups), 'LOCK_CLEANUP_TIMEOUT_NOT_PROVEN')
    return {'ok': True, 'run_id': RUN, 'diagnostic_sha256': digest(logs[0]), 'operation': proof,
            'original_failed_backup_not_adopted': True}


def verify_tools(manifest):
    hashes = manifest.get('activation_tools_sha256', {})
    require(set(hashes) == {'resume_r21.py', 'summarize_r21_baseline_failure.py'}, 'ACTIVATION_TOOLS_NOT_SEALED')
    for name, expected in hashes.items():
        path = KIT / 'tools' / name
        require(not path.is_symlink() and digest(path) == expected, 'ACTIVATION_TOOL_CHANGED')


def main():
    require(os.geteuid() == 0, 'LOCAL_SUDO_REQUIRED')
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    module = load('sealed_r22_activation', KIT / 'source/scripts/audit_release/activate.py')
    core = module.router.core
    manifest = core.verify(); verify_tools(manifest)
    job = guard_state(core, manifest)
    diag = load('sealed_r22_failure_classifier', KIT / 'tools/summarize_r21_baseline_failure.py')
    proof = guard_failure(diag)
    private = KIT / 'private'
    core.platform().no_symlinks(private)
    private.chmod(0o700); os.chown(private, 0, 0)
    operator = private / 'entry-operator.lock'; core.platform().no_symlinks(operator)
    with operator.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not (private / 'entry-started.json').exists(), 'NEW_RELEASE_ALREADY_ATTEMPTED')
        write = core.platform().write_json
        write(private / 'prior-failed-job.json', job)
        write(private / 'entry-started.json', {'release': NAME, 'started_at': datetime.now(timezone.utc).isoformat()})
        write(KIT / 'evidence/prior-failure-verified.json', proof, 0o644)
        core.call(['python3', '/usr/local/lib/homecontrol-backup-storage/migrate.py', 'check'])
        adapter = load('sealed_r22_lock_recovery_adapter', KIT / 'tools/resume_r21.py')
        adapter.KIT = KIT
        adapter.install_diagnostics(module, private)
        with ExitStack() as stack:
            core.locked(stack); core.idle()
            # Revalidate after acquiring both host locks: no intervening timer
            # run or state change may be silently adopted as this failed run.
            guard_state(core, manifest)
            guard_failure(diag)
            settings = json.loads(module.router.private_text(BASE / 'backups/backup_settings.json'))
            require(settings.get('backup_target') == 'router_ftp'
                    and settings.get('router_repository_path') == '/G/hc-backup/restic/homecontrol', 'UNEXPECTED_REPOSITORY')
            with tempfile.TemporaryDirectory(prefix='hc-r22-recovery-') as temporary:
                repo = module.router.RouterRepository(settings, cache=Path(temporary))
                repo.prepare()
                recovery = adapter.remove_stale(repo, lambda name, value: write(private / name, value))
                write(KIT / 'evidence/lock-recovery.json', recovery, 0o644)
        print('Az r21 hibája és az r18 baseline ellenőrzött. Az új r22 teljes előmentési és élesítési folyamata indul.', flush=True)
        module.main('activate')
        require(read(KIT / 'deployment-status.json').get('state') == 'deployed_and_audit_handover_complete', 'HANDOVER_NOT_COMPLETE')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try: main()
    except BaseException as error:
        if os.geteuid() == 0:
            try:
                path = KIT / 'private/entry-error.json'
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump({'error_type': type(error).__name__, 'detail': str(error)}, stream)
            except OSError: pass
        code = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_]+', str(error)) else type(error).__name__
        print('Az r22 megállt: ' + code + '. A privát napló megőrizve; ne ismételd vakon.', file=sys.stderr)
        raise SystemExit(1)
