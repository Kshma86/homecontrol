"""Capture a router snapshot failure without deploying or running retention."""
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import uuid

BASE = Path('/srv/docker/homecontrol')
KIT = BASE / 'backups/releases/hc-audit-20261102-r20'
RUN = '41f46eaa18d647e2bacb2be85adb839e'
ARCHIVE = 'homecontrol_2026-11-02_22-03-38_' + RUN + '.tar.gz'
EVIDENCE = BASE / 'docs/audit-evidence/r20-router-failure-20261102'


def classify(text):
    text = str(text).lower()
    patterns = {'source_missing': ('no such file or directory', 'file does not exist'),
                'source_changed': ('file has changed', 'file changed', 'size changed'),
                'permission_denied': ('permission denied', 'access denied'),
                'disk_full': ('no space left', 'disk full', 'quota exceeded'),
                'io_error': ('input/output error', 'i/o error'),
                'transport': ('connection reset', 'broken pipe', 'unexpected eof', 'timeout', 'timed out', 'connection refused'),
                'repository_locked': ('repository is already locked', 'unable to create lock'),
                'source_read_errors': ('could not be read', 'unable to save snapshot', 'incomplete snapshot'),
                'crypto_or_corruption': ('ciphertext verification failed', 'invalid data returned', 'hash does not match')}
    return [name for name, values in patterns.items() if any(value in text for value in values)] or ['unclassified_private_detail_retained']


def source_group(path):
    path = str(path)
    for prefix, group in (('/var/lib/docker/volumes/', 'docker_volumes'),
                          (str(BASE / 'homeassistant') + '/', 'homeassistant'),
                          (str(BASE / 'infra/ssh') + '/', 'private_release_credentials_or_image_cache'),
                          (str(BASE / 'scripts') + '/', 'scripts_and_frozen_runtimes'),
                          (str(BASE / 'infra') + '/', 'infrastructure'),
                          (str(BASE / 'apps') + '/', 'applications'),
                          (str(BASE / 'media') + '/', 'media')):
        if path.startswith(prefix):
            return group
    return 'other'


def summarize_errors(stdout, stderr):
    errors = []
    summaries = []
    for line in (stdout + '\n' + stderr).splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        if message.get('message_type') == 'error':
            item = str(message.get('item', ''))
            public_path = 'withheld'
            for prefix, label in ((str(BASE) + '/', '<project>/'), ('/var/lib/docker/volumes/', '<docker-volumes>/')):
                if item.startswith(prefix):
                    relative = item[len(prefix):]
                    if (len(relative) <= 240 and re.fullmatch(r'[a-zA-Z0-9_./ -]+', relative)
                            and '..' not in Path(relative).parts):
                        public_path = label + re.sub(r'(?<![a-zA-Z0-9])[0-9a-f]{32,}(?![a-zA-Z0-9])', '<id>', relative)
            errors.append({'source_group': source_group(item), 'item': public_path,
                           'during': message.get('during') if message.get('during') in ('archival', 'scan') else 'other',
                           'classes': classify(message.get('error'))})
        if message.get('message_type') == 'summary':
            sid = message.get('snapshot_id', '')
            if re.fullmatch('[0-9a-f]{8,64}', sid):
                summaries.append(sid)
    return errors, summaries


def summarize_latest():
    if os.geteuid() != 0:
        raise PermissionError('Local sudo is required to summarize private diagnostic logs')
    candidates = [path for path in (KIT / 'private').glob('snapshot-diagnosis-*')
                  if re.fullmatch(r'snapshot-diagnosis-\d{8}T\d{6}Z-[0-9a-f]{8}', path.name)
                  and not path.is_symlink() and path.stat().st_uid == 0]
    if not candidates:
        raise ValueError('No diagnostic logs exist')
    work = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    stdout, stderr = work / 'snapshot_probe.stdout', work / 'snapshot_probe.stderr'
    if not stdout.is_file() or not stderr.is_file():
        raise ValueError('The diagnostic snapshot has not finished or was not started')
    for path in (stdout, stderr):
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
            raise ValueError('Unexpected private log ownership or permissions')
    errors, snapshots = summarize_errors(stdout.read_text(), stderr.read_text())
    result = {'read_only_summary': True, 'new_remote_commands': 0,
              'source_errors': errors, 'snapshot_summary_ids': snapshots,
              'stderr_classes': classify(stderr.read_text()), 'private_detail_not_printed': True}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.chmod(0o755)
    path = EVIDENCE / ('summary-' + work.name.removeprefix('snapshot-diagnosis-') + '.json')
    path.write_text(json.dumps(result, indent=2) + '\n')
    path.chmod(0o644)
    print(json.dumps(result, indent=2), flush=True)


def main():
    if os.geteuid() != 0:
        raise PermissionError('Run with local sudo; private router credentials are required')
    sys.dont_write_bytecode = True
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    marker = json.loads((BASE / 'infra/access-release.json').read_text())
    if marker['release'] != 'hc-security-20261102-r18':
        raise ValueError('Expected restored r18; no probe started')
    if json.loads((KIT / 'deployment-status.json').read_text()).get('phase') != 'previous_release_restored':
        raise ValueError('Expected completed rollback; no probe started')
    spec = importlib.util.spec_from_file_location('r20_diagnostic_core', KIT / 'source/scripts/f10_release/deploy.py')
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    manifest = core.verify()
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    work = KIT / 'private' / ('snapshot-diagnosis-' + identifier)
    work.mkdir(mode=0o700)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.chmod(0o755)
    report = {'diagnostics_completed': False, 'deployment_performed': False,
              'retention_or_deletion_performed': False, 'diagnostic_snapshot_write_attempted': False,
              'original_run_id': RUN, 'private_log_directory': str(work)}
    sys.path.insert(0, str(KIT / 'source/infra/backend'))
    from router_backup import RouterRepository, private_text
    from backup_protocol import verify_archive
    with ExitStack() as stack:
        core.locked(stack)
        core.idle()
        state = json.loads((BASE / 'backups/backup-state.json').read_text())
        if state.get('run_id') != RUN or state.get('state') != 'failed':
            raise ValueError('Backup state changed; no probe started')
        for name, before in manifest['baseline'].items():
            row = json.loads(core.call(['docker', 'inspect', name]).stdout)[0]
            if row['Image'] != before['image']:
                raise ValueError('Restored image mismatch; no probe started')
            if name in manifest['unchanged'] and row['Id'] != before['id']:
                raise ValueError('Unchanged platform replaced; no probe started')
        settings = json.loads(private_text(BASE / 'backups/backup_settings.json'))
        if settings.get('backup_target') != 'router_ftp' or settings.get('router_repository_path') != '/G/hc-backup/restic/homecontrol':
            raise ValueError('Unexpected router target')
        archive = BASE / 'backups' / ARCHIVE
        receipt = json.loads(Path(str(archive) + '.complete.json').read_text())
        print('A megőrzött helyi archívum teljes ellenőrzése; szolgáltatásváltás nem történik.', flush=True)
        checked = verify_archive(archive)
        if (receipt.get('run_id') != RUN or receipt.get('completed') is not True
                or checked['sha256'] != receipt.get('sha256')):
            raise ValueError('Local archive mismatch')
        report['archive_verified'] = checked
        with tempfile.TemporaryDirectory(prefix='hc-router-failure-cache-') as cache:
            repo = RouterRepository(settings, cache=Path(cache))
            repo.prepare()
            def run(phase, arguments):
                result = subprocess.run(repo.command + arguments, env=repo.env, capture_output=True,
                                        text=True, timeout=10800)
                for field in ('stdout', 'stderr'):
                    path = work / (phase + '.' + field)
                    path.write_text(getattr(result, field))
                    path.chmod(0o600)
                return result
            print('Csak olvasó repository-metaadat és teljes adatellenőrzés.', flush=True)
            inventory = run('snapshots_before', ['--no-lock', 'snapshots', '--json'])
            if inventory.returncode:
                report['inventory_exit_code'] = inventory.returncode
                report['inventory_error_classes'] = classify(inventory.stderr)
            else:
                rows = json.loads(inventory.stdout)
                report['existing_snapshots_for_failed_archive'] = [row['id'] for row in rows
                    if str(archive) in row.get('paths', []) and re.fullmatch('[0-9a-f]{64}', row.get('id', ''))]
                check = run('check_before', ['--no-lock', 'check', '--read-data'])
                report['repository_check_exit_code'] = check.returncode
                report['repository_check_error_classes'] = classify(check.stderr) if check.returncode else []
                if check.returncode == 0:
                    sources = [archive] + [BASE / n for n in ('apps', 'infra', 'homeassistant', 'scripts') if (BASE / n).is_dir()]
                    if settings.get('include_docker_volumes', True) is True and Path('/var/lib/docker/volumes').is_dir():
                        sources.append(Path('/var/lib/docker/volumes'))
                    if settings.get('include_media', True) is True and (BASE / 'media').is_dir():
                        sources.append(BASE / 'media')
                    patterns = [str(BASE / n) for n in ('infra/postgres/data', 'infra/mqtt/data', 'infra/mqtt/log',
                                 'infra/zigbee2mqtt/data/log', 'apps/tuya-poller/logs', '**/__pycache__')]
                    args = ['backup', '--json', '--tag', 'hc-r20-diagnostic']
                    for pattern in patterns:
                        args += ['--exclude', pattern]
                    args += ['--'] + [str(path) for path in sources]
                    print('Egy külön címkéjű diagnosztikai snapshot indul; megőrzés/törlés és átállítás nélkül.', flush=True)
                    report['diagnostic_snapshot_write_attempted'] = True
                    result = run('snapshot_probe', args)
                    report['snapshot_probe_exit_code'] = result.returncode
                    report['snapshot_probe_error_classes'] = classify(result.stderr) if result.returncode else []
                    errors, summaries = summarize_errors(result.stdout, result.stderr)
                    report['source_errors'] = errors
                    report['snapshot_summary_ids'] = summaries
            report['diagnostics_completed'] = True
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    path = EVIDENCE / ('diagnosis-' + identifier + '.json')
    core.platform().write_json(path, report, 0o644)
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--summarize-latest']:
            summarize_latest()
        elif sys.argv[1:] == ['--supervised-worker']:
            main()
        elif sys.argv[1:]:
            raise ValueError('Unexpected diagnostic arguments')
        else:
            if os.geteuid() != 0:
                raise PermissionError('Local sudo is required')
            unit = 'homecontrol-r20-snapshot-diagnosis.service'
            state = subprocess.run(['systemctl', 'show', unit, '--property=LoadState', '--value'], capture_output=True, text=True, check=False)
            if state.stdout.strip() != 'not-found':
                raise ValueError('A diagnostic supervisor already exists')
            helper_path = BASE / 'backups/releases/hc-audit-20261102-r20-continuation-1/source/backup_supervision.py'
            spec = importlib.util.spec_from_file_location('diagnostic_supervision', helper_path)
            helper = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(helper)
            def interrupt(*_):
                raise InterruptedError('Diagnostic interrupted')
            signal.signal(signal.SIGTERM, interrupt)
            try:
                result = subprocess.run(helper.command([sys.executable, str(Path(__file__).resolve()), '--supervised-worker'], unit=unit), timeout=helper.CLIENT_SECONDS)
                if result.returncode:
                    raise RuntimeError('Diagnostic worker did not complete')
            except BaseException:
                subprocess.run(['systemctl', 'stop', unit], timeout=120, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                raise
    except BaseException as error:
        print('A diagnosztika megállt: ' + type(error).__name__ + '; élesítés nem történt.', file=sys.stderr)
        raise SystemExit(1)
