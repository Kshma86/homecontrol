"""Read the recorded r21 baseline failure; no processes or remote operations."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys

BASE = Path('/srv/docker/homecontrol')
RUN = '37e3acdd8a374fc4a2a48422ab830ed5'
KIT = BASE / 'backups/releases/hc-audit-20261102-r21'
SIDECAR = BASE / 'backups/releases/hc-audit-20261102-r21-continuation-2'
LIMIT = 16 * 1024 ** 2
TOKENS = {
    'repository_locked': ('repository is already locked', 'unable to create lock', 'locked exclusively'),
    'disk_full': ('no space left', 'disk full', 'quota exceeded', 'insufficient storage'),
    'read_only_filesystem': ('read-only file system', 'read only filesystem'),
    'permission': ('permission denied', 'access denied'),
    'credentials': ('wrong password', 'no key found', 'login incorrect', 'authentication failed'),
    'transport': ('connection reset', 'broken pipe', 'unexpected eof', 'timeout', 'timed out',
                  'connection refused', 'connection closed', 'connection lost', 'i/o timeout'),
    'missing_file': ('no such file or directory', 'does not exist', 'not found'),
    'source_changed': ('file has changed', 'file changed', 'size changed'),
    'source_read_errors': ('could not be read', 'incomplete snapshot'),
    'io_error': ('input/output error', 'i/o error'),
    'crypto_or_corruption': ('ciphertext verification failed', 'invalid data returned', 'hash does not match'),
    'backend_write': ('failed to save', 'unable to save', 'failed to upload', 'upload failed', 'failed to write'),
    'backend_listing': ('failed to list', 'unable to list'),
    'file_exists': ('file exists', 'already exists'),
    'unsupported_operation': ('not implemented', 'not supported', 'unsupported'),
    'unexpected_status': ('unexpected status', 'unexpected response'),
}


def classes(value):
    text = str(value).lower()
    return [name for name, terms in TOKENS.items() if any(term in text for term in terms)]


def read_private(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('PRIVATE_LOG_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('PRIVATE_LOG_PERMISSIONS')
        if info.st_size > LIMIT:
            raise ValueError('PRIVATE_LOG_TOO_LARGE')
        payload = stream.read(LIMIT + 1)
        if len(payload) > LIMIT:
            raise ValueError('PRIVATE_LOG_TOO_LARGE')
    return json.loads(payload)


def group(item):
    value = str(item)
    for root, name in ((BASE / 'backups', 'backup_archive'),
                       (BASE / 'homeassistant', 'homeassistant'),
                       (BASE / 'infra/ssh', 'release_credentials_or_image_cache'),
                       (BASE / 'infra', 'infrastructure'),
                       (BASE / 'apps', 'applications'),
                       (BASE / 'scripts', 'scripts_and_runtimes'),
                       (Path('/var/lib/docker/volumes'), 'docker_volumes')):
        if value.startswith(str(root) + '/'):
            return name
    return 'other'


def summary(payload):
    stdout, stderr = str(payload.get('stdout', '')), str(payload.get('stderr', ''))
    text = stdout + '\n' + stderr
    errors, snapshots = [], 0
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get('message_type') == 'error':
            errors.append({'source_group': group(row.get('item', '')),
                           'during': row.get('during') if row.get('during') in ('scan', 'archival') else 'other',
                           'classes': classes(row.get('error', ''))})
        if row.get('message_type') == 'summary':
            snapshots += bool(re.fullmatch('[0-9a-f]{8,64}', str(row.get('snapshot_id', ''))))
    code = payload.get('exit_code')
    return {
        'tool': payload.get('tool') if payload.get('tool') in ('restic', 'rclone') else 'withheld',
        'operation': payload.get('operation') if payload.get('operation') in
            ('backup', 'snapshots', 'check', 'forget', 'lsf', 'version', 'restore') else 'withheld',
        'exit_code': code if type(code) is int and -127 <= code <= 255 else None,
        'error_classes': classes(text) or ['unclassified_private_detail_retained'],
        'ftp_reply_codes': sorted(set(re.findall(r'\b(?:421|425|426|450|451|452|500|501|502|504|530|532|550|551|552|553)\b', stderr))),
        'source_error_count': len(errors), 'source_errors': errors[:40],
        'snapshot_summaries': snapshots,
        'stdout_truncated': payload.get('stdout_truncated') is True,
        'stderr_truncated': payload.get('stderr_truncated') is True,
        'raw_detail_withheld': True,
    }


def main():
    if os.geteuid() != 0:
        raise PermissionError('LOCAL_SUDO_REQUIRED')
    marker = json.loads((BASE / 'infra/access-release.json').read_text())
    state = json.loads((BASE / 'backups/backup-state.json').read_text())
    deployment = json.loads((KIT / 'deployment-status.json').read_text())
    if marker.get('release') != 'hc-security-20261102-r18':
        raise ValueError('ACTIVE_RELEASE_CHANGED')
    if state.get('run_id') != RUN or state.get('state') != 'failed':
        raise ValueError('BACKUP_RUN_CHANGED')
    if deployment.get('phase') != 'baseline_full_backup':
        raise ValueError('DEPLOYMENT_PHASE_CHANGED')
    work = BASE / 'backups/router-diagnostics'
    logs = sorted(p for p in work.glob(RUN + '-*.json')
                  if re.fullmatch(RUN + r'-[0-9a-f]{32}\.json', p.name))
    if not logs or len(logs) > 32:
        raise ValueError('EXPECTED_DIAGNOSTIC_LOGS_NOT_FOUND')
    records = []
    for path in logs:
        payload = read_private(path)
        if payload.get('run_id') != RUN:
            raise ValueError('DIAGNOSTIC_RUN_MISMATCH')
        records.append(summary(payload))
    error = read_private(SIDECAR / 'private/capacity-continuation-error.json')
    result = {
        'checked_at': datetime.now(timezone.utc).isoformat(), 'read_only': True,
        'remote_commands': 0, 'deployment_performed': False,
        'active_release': marker['release'], 'run_id': RUN,
        'phase': deployment['phase'],
        'continuation_error_type': error.get('error_type') if error.get('error_type') in
            ('RuntimeError', 'ValueError', 'TimeoutExpired', 'PermissionError') else 'withheld',
        'continuation_error_classes': classes(error.get('detail', '')),
        'private_log_count': len(records), 'operations': records,
        'new_transition_exists': (KIT / 'private/transition').exists(),
        'new_runtime_exists': (BASE / 'scripts/access_runtime/hc-audit-20261102-r21').exists(),
        'raw_detail_withheld': True,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        main()
    except Exception as error:
        code = str(error) if isinstance(error, (ValueError, PermissionError)) and re.fullmatch('[A-Z_]+', str(error)) else type(error).__name__
        print('A naplóösszesítés megállt: ' + code + '. Éles művelet nem történt.', file=sys.stderr)
        raise SystemExit(1)
