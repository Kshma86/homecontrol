#!/usr/bin/env python3
"""Check the deployed r14 repository and retry its configured retention safely."""
import configparser
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

BASE = Path('/srv/docker/homecontrol')
RELEASE = 'hc-router-backup-20261101-r14'
UNITS = ('homecontrol-ai-weekly-backup.service', 'homecontrol-restic-check.service')


def redact(message, secrets):
    for secret in sorted(set(secrets) - {''}, key=len, reverse=True):
        message = message.replace(secret, '[REDACTED]')
    return re.sub(r'(://[^\s/:]+:)[^\s/@]+@', r'\1[REDACTED]@', message)


def maintain(repo, report):
    # Do not prune a repository that failed its full content check.
    report['phase'] = 'check_before_retention'
    repo.check()
    report['check_before'] = 'verified'
    report['phase'] = 'retention'
    repo.retention()
    report['retention'] = 'verified'
    report['phase'] = 'check_after_retention'
    repo.check()
    report['check_after'] = 'verified'
    report['phase'] = 'completed'
    report['ok'] = True


def main():
    if os.geteuid() != 0:
        raise PermissionError('A privát FTP-beállításokhoz helyi sudo szükséges.')
    sys.dont_write_bytecode = True
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    kit = BASE / 'backups/releases' / RELEASE
    runtime = BASE / 'scripts/access_runtime' / RELEASE
    marker = json.loads((BASE / 'infra/access-release.json').read_text())
    if marker.get('release') != RELEASE:
        raise ValueError('Másik kiadás aktív; ez az ellenőrző csak az r14-hez tartozik.')
    manifest = json.loads((kit / 'release.json').read_text())
    for name in ('infra/backend/router_backup.py', 'infra/backend/backup_protocol.py'):
        actual = hashlib.sha256((runtime / name).read_bytes()).hexdigest()
        if actual != manifest['source_sha256'][name]:
            raise ValueError('A telepített mentőmodul eltér a lezárt csomagtól.')
    sys.path.insert(0, str(runtime / 'infra/backend'))
    from router_backup import RouterRepository, private_text

    settings = json.loads(private_text(BASE / 'backups/backup_settings.json'))
    if (settings.get('backup_target') != 'router_ftp'
            or settings.get('router_repository_path') != '/G/hc-backup/restic/homecontrol'):
        raise ValueError('Nem a jóváhagyott routeres cél aktív.')
    if not settings.get('restic_enabled'):
        raise ValueError('A routeres karbantartás felfüggesztve; használja a csak olvasó diagnosztikát.')
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(private_text(settings['router_rclone_config']))
    obscured = config[settings['router_rclone_remote']]['pass']
    secrets = [obscured, private_text(settings['restic_password_file']).strip()]
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    log_path = kit / 'private' / ('router-maintenance-' + identifier + '.log')
    report_path = kit / 'evidence' / ('router-maintenance-' + identifier + '.json')
    report = {'release': RELEASE, 'ok': False, 'started_at': datetime.now(timezone.utc).isoformat()}
    last = {}
    with (BASE / 'backups/homecontrol-backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as log, tempfile.TemporaryDirectory(prefix='hc-router-maintenance-') as work:
            def run(args, **kwargs):
                result = subprocess.run(args, **kwargs)
                last.clear()
                last.update(returncode=result.returncode, stderr=result.stderr or '')
                log.write('\nPhase: ' + report.get('phase', 'prepare') + '\n')
                log.write(result.stdout or '')
                log.write(result.stderr or '')
                log.flush()
                return result

            try:
                repo = RouterRepository(settings, run=run, cache=Path(work) / 'cache')
                print('Teljes visszaolvasás → beállított megőrzés → ismételt tartalomellenőrzés.', flush=True)
                maintain(repo, report)
            except Exception as error:
                report['error_type'] = type(error).__name__
                report['exit_code'] = last.get('returncode')
                diagnostic = redact(last.get('stderr', ''), secrets)[-4000:]
                print('Szakasz: ' + report.get('phase', 'prepare'), flush=True)
                if diagnostic.strip():
                    print(diagnostic, flush=True)
                print('Privát részletes napló: ' + str(log_path), flush=True)
            if report['ok']:
                # The actual check above passed; clear only these old service failures.
                result = subprocess.run(['systemctl', 'reset-failed', *UNITS],
                                        capture_output=True, text=True, timeout=30)
                report['failed_units_reset'] = result.returncode == 0
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        fd = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, 'w') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BlockingIOError:
        raise SystemExit('Másik mentés fut; az ellenőrző nem indult el.')
    except Exception as error:
        raise SystemExit('Az ellenőrző nem indult el: ' + type(error).__name__)
