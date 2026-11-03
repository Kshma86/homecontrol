"""Summarize the used r22 continuation; read files only, never activate a release."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-audit-20261103-r22'
KIT = BASE / 'backups/releases' / NAME
SIDECAR = BASE / 'backups/releases/hc-audit-20261103-r22-continuation-1'
MANIFEST_SHA256 = '96577f442a6457bb42a85a127a0e8b2d1f166848242ed4f724d705354fa1aa8c'
EXACT = (
    'New release is not active', 'Deployed runtime differs from sealed source',
    'AI/router policy changed', 'Expected a read-only system schedule plan',
    'Expected five configured router backup timers',
    'Invalid backup settings; no schedule changes made', 'Invalid weekly backup calendar',
)
PREFIXES = (
    'Unexpected live image: ', 'Unchanged container replaced: ',
    'Component is not running: ', 'Unhealthy component: ',
    'Conflicting expected unit: ', 'Backup unit changed: ',
    'Scheduled unit enablement differs: ', 'Scheduled unit active state differs: ',
    'Scheduled timer has no next trigger: ',
)


def read(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Protected input is a symlink')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 ** 2:
            raise ValueError('Invalid diagnostic input')
        return json.loads(stream.read(4 * 1024 ** 2 + 1))


def classify(error, names):
    kind = error.get('error_type')
    result = {'error_type': kind if kind in ('ValueError', 'RuntimeError', 'Error',
              'PermissionError', 'FileNotFoundError', 'TimeoutExpired', 'ResumeError') else 'withheld',
              'recognized': False, 'raw_detail_withheld': True}
    detail = error.get('detail')
    if not isinstance(detail, str):
        return result
    if detail in EXACT:
        result.update(recognized=True, condition=detail)
    else:
        for prefix in PREFIXES:
            # The entire suffix must equal a sealed, public name. Never echo
            # arbitrary log text, URLs, credentials, paths or multiline tails.
            if detail.startswith(prefix) and detail[len(prefix):] in names:
                result.update(recognized=True, condition=prefix.rstrip(': '),
                              component=detail[len(prefix):])
                break
    return result


def summarize():
    if os.geteuid() != 0:
        raise PermissionError('Local sudo is required')
    if hashlib.sha256((KIT / 'release.json').read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Sealed manifest changed')
    manifest = read(KIT / 'release.json')
    names = set(manifest['baseline'])
    for root in (KIT / 'source/scripts/systemd',):
        names.update(p.name for p in root.rglob('*') if p.suffix in ('.service', '.timer', '.path'))
    names.update(('homecontrol-post-boot-health.service.d/hc-access.conf',
                  'homecontrol-backup-apply.service.d/hc-access.conf',
                  'homecontrol-hostops.service.d/hc-access.conf', 'docker.service.d/hc-access.conf',
                  'homecontrol-mqtt-access.service'))
    error = read(SIDECAR / 'private/continuation-error.json')
    result = read(KIT / 'private/transition/result.json')
    marker = read(BASE / 'infra/access-release.json')
    status = read(KIT / 'deployment-status.json')
    accepted = read(KIT / 'evidence/router-live-acceptance.json')
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'read_only': True, 'remote_commands': 0, 'deployment_performed': False,
        'active_release': marker.get('release') if marker.get('release') in
            (NAME, 'hc-security-20261102-r18') else 'other',
        'rollback_verified': result == {'state': 'rolled_back', 'success': True}
            and status.get('phase') == 'previous_release_restored',
        'handover_exists': (BASE / 'docs/audit-final-20261102.md').exists(),
        'recorded_error': classify(error, names),
        'prior_router_restore_receipt_ok': accepted.get('ok') is True
            and accepted.get('release') == NAME
            and accepted.get('restore') == 'verified' and accepted.get('database') == 'verified',
        'note': 'A successful intermediate restore receipt does not mean the release is currently active.',
    }


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        print(json.dumps(summarize(), indent=2))
    except Exception as error:
        print(json.dumps({'ok': False, 'error_type': type(error).__name__,
                          'read_only': True, 'raw_detail_withheld': True}))
        raise SystemExit(1)
