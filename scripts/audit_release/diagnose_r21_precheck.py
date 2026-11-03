"""Read-only r21 failure diagnosis; no deployment, unlock, repair or retention."""
from contextlib import ExitStack
from datetime import datetime, timezone
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
KIT = BASE / 'backups/releases/hc-audit-20261102-r21'
UNIT = 'homecontrol-r21-precheck-diagnosis.service'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classes(value):
    text = value.lower()
    tokens = {
        'repository_locked': ('repository is already locked', 'unable to create lock', 'locked exclusively'),
        'missing_packs': ('does not exist', 'missing pack'),
        'transport': ('connection reset', 'broken pipe', 'unexpected eof', 'timeout', 'timed out', 'connection refused', 'failed to list'),
        'disk_full': ('no space left', 'disk full', 'quota exceeded'),
        'permission': ('permission denied', 'access denied'),
        'crypto_or_corruption': ('ciphertext verification failed', 'invalid data returned', 'hash does not match'),
        'credentials': ('wrong password', 'no key found', '530 login', 'authentication failed'),
    }
    return [name for name, terms in tokens.items() if any(term in text for term in terms)]


def safe_error(error):
    detail = str(error.get('detail', ''))
    match = re.fullmatch(r'Restic operation failed \(exit (\d+)\); repository was not reinitialized', detail)
    kind = error.get('error_type')
    return {'error_type': kind if kind in ('RuntimeError', 'ValueError', 'TimeoutExpired', 'PermissionError') else 'withheld',
            'restic_exit_code': int(match[1]) if match else None,
            'error_classes': classes(detail), 'raw_detail_withheld': True}


def read_operation(repo, arguments, work, label, *, run=subprocess.run):
    # A positive command allowlist makes destructive operations impossible here.
    if arguments not in (['list', 'locks'], ['check', '--read-data']):
        raise ValueError('Diagnostic operation is not allowed')
    timed_out = False
    command = [repo.command[0], '--no-lock', *repo.command[1:], *arguments]
    try:
        result = run(command, env=repo.env, check=False, capture_output=True, text=True, timeout=10800)
    except subprocess.TimeoutExpired as error:
        timed_out = True
        result = subprocess.CompletedProcess(command, 124, error.stdout or '', error.stderr or '')
    for field in ('stdout', 'stderr'):
        path = work / (label + '.' + field)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            value = getattr(result, field) or ''
            stream.write(value.decode(errors='replace') if isinstance(value, bytes) else value)
    if isinstance(result.stdout, bytes): result.stdout = result.stdout.decode(errors='replace')
    if isinstance(result.stderr, bytes): result.stderr = result.stderr.decode(errors='replace')
    text = (result.stdout or '') + '\n' + (result.stderr or '')
    missing = {match[1] for match in re.finditer(r'\bpack ([0-9a-f]{8,64}): does not exist\b', text)}
    report = {'exit_code': result.returncode, 'error_classes': (classes(text) or ['unclassified_private_detail_retained']) if result.returncode else [],
              'missing_pack_count': len(missing), 'timed_out': timed_out}
    if arguments == ['list', 'locks']:
        report['lock_count'] = sum(bool(re.fullmatch('[0-9a-f]{64}', row.strip())) for row in (result.stdout or '').splitlines())
    return report


def validate_state(core, manifest):
    core.guard_runtime(manifest)
    if core.STATE.exists() or core.RUNTIME.exists() or core.PRIVATE.exists():
        raise ValueError('Unexpected r21 cutover state; diagnosis refused')


def worker():
    if os.geteuid() != 0:
        raise PermissionError('Local sudo required')
    sys.dont_write_bytecode = True
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    core = load_module('r21_diagnostic_core', KIT / 'source/scripts/f10_release/deploy.py')
    manifest = core.verify()
    validate_state(core, manifest)
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    work = KIT / 'private' / ('precheck-diagnosis-' + identifier)
    work.mkdir(mode=0o700)
    report = {'read_only_repository': True, 'remote_write_commands': 0, 'deployment_performed': False,
              'retention_unlock_or_repair_performed': False, 'diagnostics_completed': False,
              'active_release': core.OLD, 'private_log_directory': str(work),
              'original_failure': safe_error(json.loads((KIT / 'private/audit-error.json').read_text()))}
    sys.path.insert(0, str(KIT / 'source/infra/backend'))
    from router_backup import RouterRepository, private_text
    settings = json.loads(private_text(BASE / 'backups/backup_settings.json'))
    if settings.get('backup_target') != 'router_ftp' or settings.get('router_repository_path') != '/G/hc-backup/restic/homecontrol':
        raise ValueError('Unexpected repository target')
    with ExitStack() as stack:
        core.locked(stack)
        core.idle()
        with tempfile.TemporaryDirectory(prefix='hc-r21-readonly-check-') as temporary:
            from_logger = load_module('r21_diagnostic_operation_log', KIT / 'source/scripts/router_operation_log.py')
            diagnostics = from_logger.OperationLog(work, uuid.uuid4().hex)
            repo = RouterRepository(settings, run=diagnostics, cache=Path(temporary))
            report['phase'] = 'prepare_transport'
            try:
                repo.prepare()
                print('Csak olvasó lock-lista, majd teljes repository-adatellenőrzés; javítás és törlés nélkül.', flush=True)
                report['phase'] = 'list_locks'
                report['locks_before'] = read_operation(repo, ['list', 'locks'], work, 'locks_before')
                if report['locks_before']['exit_code'] != 0:
                    return report
                report['phase'] = 'full_data_check'
                report['check'] = read_operation(repo, ['check', '--read-data'], work, 'check')
                report['phase'] = 'completed'
                report['diagnostics_completed'] = True
                report['repository_full_data_verified'] = report['check']['exit_code'] == 0
                return report
            except Exception as error:
                report['diagnostic_error_type'] = type(error).__name__
                # Preserve full exception details only in the root-private directory.
                core.platform().write_json(work / 'error.json', {'error_type': type(error).__name__, 'detail': str(error)})
                return report
            finally:
                report['finished_at'] = datetime.now(timezone.utc).isoformat()
                core.platform().write_json(work / 'summary.json', report, 0o644)
                public = BASE / 'docs/audit-evidence/r21-precheck-20261102'
                public.mkdir(exist_ok=True)
                public.chmod(0o755)
                core.platform().write_json(public / ('diagnosis-' + identifier + '.json'), report, 0o644)
                print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)


def main():
    if os.geteuid() != 0:
        raise PermissionError('Local sudo required; no diagnostic was started')
    if sys.argv[1:] == ['--worker']:
        return worker()
    if sys.argv[1:]:
        raise ValueError('Unexpected diagnostic arguments')
    helper = load_module('r21_diagnostic_supervision', KIT / 'source/scripts/audit_release/backup_supervision.py')
    def call(args, **kwargs):
        allowed = kwargs.pop('allowed', (0,))
        kwargs.pop('extra_env', None)
        result = subprocess.run(args, capture_output=True, **kwargs)
        if result.returncode not in allowed:
            raise RuntimeError('Diagnostic supervisor failed; private summary must be inspected')
        return result
    helper.UNIT = UNIT
    # command's unit default was bound at import; use the explicit diagnostic name.
    original = helper.command
    helper.command = lambda args: original(args, unit=UNIT)
    print('R21 csak olvasó diagnosztika indul; a teljes visszaolvasás néhány percig tarthat.', flush=True)
    result = helper.supervised_call(call, [sys.executable, str(Path(__file__).resolve()), '--worker'])
    print(result.stdout.decode(errors='replace'), end='')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try:
        main()
    except Exception as error:
        print('A diagnosztika nem futott végig: ' + type(error).__name__ + '. Átállítás és repository-javítás nem történt.', file=sys.stderr)
        raise SystemExit(1)
