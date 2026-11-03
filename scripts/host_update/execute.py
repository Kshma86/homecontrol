#!/usr/bin/env python3
"""One-shot, supervised host maintenance; never invokes an HC deployment."""
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
BASE = Path('/srv/docker/homecontrol')
PREP = BASE / 'maintenance/host-update-20261103'
STATE = BASE / 'maintenance/host-update-20261103-execution'
RUNTIME = BASE / 'scripts/access_runtime/hc-audit-20261103-r22'
PREP_SHA = 'dc888e8ff821016771da676b1904608529b44a7b0e81978842a903b8d14a2c5a'
QUIESCE = ('homecontrol-backup.timer', 'homecontrol-ai-weekly-backup.timer',
           'homecontrol-restic-check.timer', 'homecontrol-log-maintenance.timer',
           'homecontrol-backup-apply.path', 'homecontrol-full-ai-backup-request.path',
           'homecontrol-post-boot-health.timer', 'apt-daily.timer', 'apt-daily-upgrade.timer')
BUSY = ('homecontrol-backup.service', 'homecontrol-ai-weekly-backup.service',
        'homecontrol-full-ai-backup-request.service', 'homecontrol-restic-check.service',
        'homecontrol-log-maintenance.service', 'homecontrol-backup-apply.service',
        'apt-daily.service', 'apt-daily-upgrade.service')
START = ('homecontrol-postgres', 'homecontrol-mqtt', 'homecontrol-ai-server',
         'homecontrol-mdns', 'homecontrol-pgbouncer', 'homeassistant', 'zigbee2mqtt',
         'homecontrol-frontend', 'homecontrol-ingest', 'homecontrol-tuya-poller',
         'homecontrol-xiaomi-x10', 'homecontrol-gree-climate',
         'homecontrol-ha-growatt-poller', 'homecontrol-backend', 'homecontrol-proxy')
COVERAGE = {'include_postgres', 'include_apps', 'include_infra', 'include_zigbee2mqtt',
            'include_homeassistant', 'include_scripts', 'include_docker_meta'}
LOG = None
PHASE = 'starting'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def write(path, value):
    temporary = Path(str(path) + '.new')
    with temporary.open('w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, indent=2); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def say(message): print(message, flush=True)


def phase(name):
    global PHASE
    PHASE = name
    write(STATE / 'progress.json', {'phase': name, 'checked_at': datetime.now(timezone.utc).isoformat()})
    say('Hostkarbantartás: ' + name)


def call(args, *, timeout=180, input=None, env=None):
    effective = {k: v for k, v in os.environ.items() if k not in
                 ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH', 'APT_CONFIG')}
    effective.update(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                     DOCKER_HOST='unix:///var/run/docker.sock', LANG='C', LC_ALL='C')
    effective.update(env or {})
    with subprocess.Popen(list(map(str, args)), stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          env=effective, start_new_session=True) as child:
        try: stdout, stderr = child.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try: stdout, stderr = child.communicate(timeout=90)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); stdout, stderr = child.communicate()
            if LOG:
                LOG.write(stdout + stderr); LOG.flush()
            raise RuntimeError('Command timed out: ' + str(args[0]))
    if LOG:
        LOG.write('\nCOMMAND ' + repr(list(map(str, args))) + '\n' + stdout + stderr); LOG.flush()
    if child.returncode: raise RuntimeError('Command failed: ' + str(args[0]))
    return stdout


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def checks():
    if sha(PREP / 'acceptance.json') != PREP_SHA: raise ValueError('Preparation seal changed')
    return load('host_maintenance_check', PREP / 'source/check.py')


def active(unit):
    return call(['systemctl', 'show', unit, '--property=ActiveState', '--value']).strip() in ('active', 'activating', 'deactivating')


def idle():
    if any(active(unit) for unit in BUSY): raise ValueError('Active backup or APT operation')
    for path in Path('/var/lib/homecontrol-hostops/jobs').glob('*.json'):
        if read(path).get('state') in ('queued', 'running'): raise ValueError('Active hostops job')
    # Other package managers must be idle; never remove or bypass dpkg/APT locks.
    for name in ('/var/lib/dpkg/lock-frontend', '/var/lib/dpkg/lock', '/var/lib/apt/lists/lock'):
        with open(name, 'a') as stream:
            fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def common_locks(stack):
    for name in ('ai-backup.lock', 'homecontrol-backup.lock'):
        path = BASE / 'backups' / name
        if path.is_symlink() or not path.is_file(): raise ValueError('Existing backup lock required')
        handle = stack.enter_context(path.open('a'))
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def physical_guard(check):
    if str(check.request('/api/xiaomi-x10/state').get('robot_state')) not in ('6', '13'):
        raise ValueError('Robot is not docked or charging')
    sql = """SELECT (SELECT count(*) FROM hc.irrigation_manual_session
      WHERE status IN ('starting','running','stop_failed')) +
      (SELECT count(*) FROM hc.irrigation_solar_pump_run WHERE status='running');"""
    command = ['docker', 'exec', '-i', 'homecontrol-postgres', 'sh', '-c',
               'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    if call(command, input=sql).strip() != '0': raise ValueError('Active irrigation session')


def validate_inventory(rows, baseline):
    actual = {r['Name'].lstrip('/'): r for r in rows}
    if set(actual) != set(baseline): raise ValueError('Container inventory differs')
    if set(START) != {name for name, row in baseline.items() if row['running']}:
        raise ValueError('Shutdown/startup inventory differs')
    for name, before in baseline.items():
        row = actual[name]
        if row['Id'] != before['id'] or row['Image'] != before['image']:
            raise ValueError('Container identity changed')
        if row['State']['Running'] != before['running']: raise ValueError('Container running state changed')
        if row['HostConfig']['RestartPolicy']['Name'] != 'unless-stopped':
            raise ValueError('Unreviewed container restart policy')


def normalize_nft(value):
    if isinstance(value, list): return [normalize_nft(v) for v in value]
    if not isinstance(value, dict): return value
    return {k: {} if k == 'counter' else normalize_nft(v)
            for k, v in value.items() if k not in ('handle', 'metainfo')}


def firewall():
    policy = read(BASE / 'infra/ssh/hc-audit-20261103-r22/network-policy.json')
    if policy.get('mode') != 'authenticated' or policy.get('owned_chain') is not True:
        raise ValueError('Unexpected MQTT firewall ownership/policy')
    result = {'policy_sha256': sha(BASE / 'infra/ssh/hc-audit-20261103-r22/network-policy.json')}
    for family in ('bridge', 'inet'):
        rows = read_nft = json.loads(call(['nft', '-j', 'list', 'table', family, 'hc41_r10']))['nftables']
        result[family] = sorted(json.dumps(normalize_nft(row), sort_keys=True) for row in rows if 'metainfo' not in row)
        if not any('rule' in row for row in read_nft): raise ValueError('MQTT firewall rules missing')
    return result


def space_guard():
    sizes = sorted((p.stat().st_size for p in (BASE / 'backups').glob('homecontrol_*.tar.gz')), reverse=True)
    required = sum(sizes[:2]) + 30 * 1024 ** 3
    for path, reserve in (('/', 8 * 1024 ** 3 + 1666223104), (BASE / 'backups', required),
                          ('/tmp', 8 * 1024 ** 3 + 1666223104)):
        info = os.statvfs(path)
        if info.f_bavail * info.f_frsize < reserve: raise ValueError('Insufficient filesystem reserve')


def validate_backup(state, smoke, previous):
    if (not state.get('run_id') or state['run_id'] == previous or state.get('mode') != 'weekly'
            or state.get('state') != 'completed' or state.get('returncode') != 0 or state.get('scope') != 'router'):
        raise ValueError('No new completed weekly router backup')
    for name in ('local_archive', 'restic', 'git_offsite', 'secrets_bundle', 'restic_retention'):
        if state.get('targets', {}).get(name, {}).get('state') != 'succeeded':
            raise ValueError('Backup target not successful: ' + name)
    receipt = state.get('archive', {})
    if (receipt.get('completed') is not True or receipt.get('run_id') != state['run_id']
            or receipt.get('mode') != 'weekly' or set(receipt.get('coverage', {})) != COVERAGE
            or any(v is not True for v in receipt['coverage'].values())): raise ValueError('Incomplete archive receipt')
    if not (smoke.get('ok') is True and smoke.get('restic') == 'sha256_verified'
            and smoke.get('database') == 'restore_verified_without_owner_acl'
            and smoke.get('filesystem') == 'sha256_verified' and smoke.get('snapshot_id')
            and smoke.get('restic_archive', {}).get('sha256') == receipt.get('sha256')
            and smoke.get('database_archive_sha256') == receipt.get('sha256')
            and smoke.get('local_archive', {}).get('sha256') == receipt.get('sha256')):
        raise ValueError('Fresh archive/router/database restore mismatch')
    return {'ok': True, 'run_id': state['run_id'], 'snapshot_id': smoke['snapshot_id'],
            'archive_sha256': receipt['sha256'], 'restore': 'verified', 'database': 'verified'}


def backup_restore(label, baseline):
    phase(label + '_full_backup')
    previous = read(BASE / 'backups/backup-state.json').get('run_id')
    call(['/usr/bin/python3', RUNTIME / 'scripts/hostops/backup_runner.py', '--mode', 'weekly'],
         timeout=11000, env={'HC_BACKUP_TIMEOUT_SECONDS': '10800'})
    state = read(BASE / 'backups/backup-state.json')
    write(STATE / (label + '-backup-private.json'), state)
    phase(label + '_router_pg_restore')
    call(['/usr/bin/python3', RUNTIME / 'scripts/restore_smoke.py', '--db-check'], timeout=7200,
         env={'HC_RESTORE_POSTGRES_IMAGE': baseline['containers']['homecontrol-postgres']['image']})
    smoke = read(BASE / 'backups/restore-smoke-result.json')
    write(STATE / (label + '-restore-private.json'), smoke)
    proof = validate_backup(state, smoke, previous)
    write(STATE / (label + '-proof.json'), proof)
    return proof


def pause():
    saved = {name: active(name) for name in QUIESCE}
    write(STATE / 'paused-units.json', saved)
    try:
        for name in QUIESCE: call(['systemctl', 'stop', name])
        end = time.monotonic() + 210
        while active('homecontrol-post-boot-health.service'):
            if time.monotonic() >= end: raise ValueError('Health service did not settle')
            time.sleep(2)
    except BaseException:
        resume(saved)
        raise
    return saved


def resume(saved):
    for name, was_active in saved.items():
        if was_active: call(['systemctl', 'start', name])


def cancel_intents():
    sys.path.insert(0, str(RUNTIME / 'scripts/access_release'))
    import climate_handover
    import common
    climate_handover.reconcile(STATE, 'deploy')
    sys.path.insert(0, str(RUNTIME / 'infra/backend'))
    from scoped_ai_power_coordination import ScopedAiPowerCoordinator
    coordinator = ScopedAiPowerCoordinator(BASE / 'backups')
    with coordinator.locked() as value:
        write(STATE / 'ai-intents-before.json', value)
        coordinator.save(common.cancel_intent(value, 'host OS maintenance'))


def start_containers(baseline):
    call(['systemctl', 'start', 'containerd.service', 'docker.service'], timeout=180)
    call(['systemctl', 'restart', 'homecontrol-mqtt-access.service'], timeout=120)
    for name in START:
        if name == 'homecontrol-backend':
            call(['systemctl', 'start', 'homecontrol-hostops.service'])
        call(['docker', 'start', baseline['containers'][name]['id']], timeout=120)
        if name in ('homecontrol-postgres', 'homecontrol-pgbouncer'):
            end = time.monotonic() + 120
            while True:
                row = json.loads(call(['docker', 'inspect', name]))[0]
                if row['State'].get('Health', {}).get('Status') == 'healthy': break
                if time.monotonic() > end: raise ValueError('Database dependency not healthy')
                time.sleep(2)


def wait_snapshot(check):
    end = time.monotonic() + 300
    while True:
        try: return check.snapshot()
        except Exception:
            if time.monotonic() >= end: raise
            time.sleep(3)


def device_connections():
    bridge = call(['docker', 'exec', 'homecontrol-backend', 'python', '/app/mqtt_read_probe.py',
                   '--topic', 'zigbee/bridge/state'], timeout=45)
    try: payload = json.loads(bridge)
    except json.JSONDecodeError: payload = bridge.strip()
    bridge_state = payload.get('state') if isinstance(payload, dict) else payload
    if bridge_state != 'online': raise ValueError('Zigbee MQTT bridge is not online')
    probe = """import os, requests
base = os.environ['HA_BASE_URL'].rstrip('/')
response = requests.get(base + '/api/states/sensor.pyl0chj016_output_power',
    headers={'Authorization': 'Bearer ' + os.environ['HA_TOKEN']}, timeout=10)
response.raise_for_status()
assert str(response.json().get('state', '')).strip().lower() not in ('', 'unknown', 'unavailable', 'none')
"""
    call(['docker', 'exec', 'homecontrol-ha-growatt-poller', 'python', '-c', probe], timeout=30)
    return {'zigbee_mqtt_bridge': 'online', 'growatt_ha_entity': 'available', 'actuation_commands': 0}


def upgrade():
    check = checks()
    phase('preflight')
    check.main('verify')
    baseline = check.snapshot()
    prepared_baseline = read(PREP / 'host-baseline.json')
    check.validate_reboot(baseline, prepared_baseline, require_reboot=False)
    if baseline['boot_id'] != prepared_baseline['boot_id']: raise ValueError('Host boot changed since preparation')
    write(STATE / 'before.json', baseline)
    if baseline['dpkg_audit'] or baseline['holds']: raise ValueError('Unreviewed package state')
    validate_inventory(json.loads(call(['docker', 'inspect', *baseline['containers']])), baseline['containers'])
    physical_guard(check); idle(); space_guard()
    call(['/usr/bin/python3', '/usr/local/lib/homecontrol-backup-storage/migrate.py', 'check'])
    check.verify_runtime_schedules()
    before_firewall = firewall(); write(STATE / 'firewall-before.json', before_firewall)
    with ExitStack() as stack: common_locks(stack)
    phase('private_host_configuration_backup')
    paths = ['/etc', '/var/lib/dpkg', '/var/lib/apt/extended_states', '/boot']
    call(['tar', '--acls', '--xattrs', '--numeric-owner', '-cpf', STATE / 'host-config.tar', *paths], timeout=300)
    write(STATE / 'host-config-sha256.json', {'sha256': sha(STATE / 'host-config.tar')})
    for label, args in {'routes': ['ip', '-j', 'route', 'show', 'table', 'all'],
                        'units': ['systemctl', 'list-unit-files', '--no-pager'],
                        'firewall-all': ['nft', '-j', 'list', 'ruleset']}.items():
        (STATE / (label + '.txt')).write_text(call(args))
    saved = {}; quiescent = False; hostops_stopped = False
    try:
        saved = pause(); idle()
        backup_restore('pre', baseline)
        # Recheck the plan after the potentially long backup, before any shutdown.
        check.main('verify'); physical_guard(check); idle(); space_guard()
        with ExitStack() as stack:
            common_locks(stack)
            call(['systemctl', 'stop', 'homecontrol-hostops.service'], timeout=240)
            hostops_stopped = True
            idle(); physical_guard(check)
            validate_inventory(json.loads(call(['docker', 'inspect', *baseline['containers']])), baseline['containers'])
            phase('ordered_shutdown'); quiescent = True
            call(['docker', 'stop', '--time', '60', 'homecontrol-backend'], timeout=100)
            cancel_intents()
            for name in reversed(START):
                if name != 'homecontrol-backend':
                    call(['docker', 'stop', '--time', '60', baseline['containers'][name]['id']], timeout=100)
            if call(['docker', 'ps', '-q']).strip(): raise ValueError('A container is still running')
            phase('installing_reviewed_packages')
            check.main('verify')
            plan = check.verify_package()
            command = ['apt-get', '-c', str(PREP / 'apt/install-reviewed.conf'),
                       '--no-download', '--no-remove', '--with-new-pkgs', 'upgrade']
            simulated = check.p.parse_simulation(call([*command, '--simulate']))
            expected = [{k: v for k, v in row.items() if k != 'catalog'} for row in plan['transactions']]
            if simulated != expected: raise ValueError('Final APT simulation differs')
            call([*command, '--assume-yes', '-o', 'Dpkg::Options::=--force-confold'], timeout=3600,
                 env={'DEBIAN_FRONTEND': 'noninteractive', 'NEEDRESTART_MODE': 'l'})
            if call(['dpkg', '--audit']).strip(): raise ValueError('dpkg audit failed')
            phase('ordered_startup')
            start_containers(baseline)
            if firewall() != before_firewall: raise ValueError('MQTT firewall differs after package install')
        resume(saved); saved = {}
        wait_snapshot(check)
        phase('before_reboot_acceptance')
        check.main('before-reboot')
        write(STATE / 'pre-reboot-device-connections.json', device_connections())
        write(STATE / 'upgrade-success.json', {'ok': True, 'state': 'upgraded_pending_reboot',
              'boot_id': baseline['boot_id'], 'reboot_performed': False})
        phase('upgraded_pending_reboot')
    finally:
        # Before shutdown a failure can safely restore the paused schedules.
        # After shutdown/partial APT, preserve evidence and require reconciliation.
        if not quiescent:
            if hostops_stopped: call(['systemctl', 'start', 'homecontrol-hostops.service'])
            if saved: resume(saved)


def finish():
    if not read(STATE / 'upgrade-success.json').get('ok'): raise ValueError('Upgrade not accepted')
    check = checks(); phase('post_boot_acceptance')
    check.main('postcheck')
    if firewall() != read(STATE / 'firewall-before.json'): raise ValueError('Post-boot MQTT firewall differs')
    write(STATE / 'post-boot-device-connections.json', device_connections())
    physical_guard(check); idle(); space_guard()
    saved = pause()
    try: proof = backup_restore('post', read(STATE / 'before.json'))
    finally: resume(saved)
    check.main('postcheck')
    write(STATE / 'finish-success.json', {'ok': True, 'state': 'host_updated_reboot_backup_restore_verified',
          'kernel': call(['uname', '-r']).strip(), **proof})
    phase('host_updated_reboot_backup_restore_verified')


def worker(action):
    global LOG
    LOG = (STATE / (action + '-private.log')).open('x')
    try:
        with (STATE / 'execution.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if action == 'upgrade': upgrade()
            elif action == 'finish': finish()
            else: raise ValueError('Unknown worker action')
    except BaseException as error:
        traceback.print_exc(file=LOG); LOG.flush()
        write(STATE / (action + '-failure.json'), {'ok': False, 'phase': PHASE, 'error_type': type(error).__name__})
        say('Megállt: ' + type(error).__name__ + '. Fázis: ' + PHASE + '. A privát napló megőrizve; ne ismételd vakon.')
        raise SystemExit(1)
    finally: LOG.close()


def main():
    os.umask(0o077)
    if os.geteuid() != 0: raise PermissionError('Local sudo authentication is required')
    if sys.argv[1:] == ['status']:
        if not STATE.exists():
            print(json.dumps({'started': False, 'packages_installed_by_this_executor': False})); return
        if STATE.is_symlink() or STATE.stat().st_uid != 0: raise ValueError('Private execution directory required')
        result = {'started': True, 'progress': read(STATE / 'progress.json') if (STATE / 'progress.json').exists() else None}
        for name in ('upgrade-failure', 'upgrade-success', 'finish-failure', 'finish-success'):
            path = STATE / (name + '.json')
            if path.exists(): result[name] = read(path)
        print(json.dumps(result, indent=2)); return
    if len(sys.argv) == 3 and sys.argv[1] == '_worker':
        info = STATE.stat()
        if STATE.is_symlink() or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('Root-owned private execution directory required')
        worker(sys.argv[2]); return
    if sys.argv[1:] not in (['upgrade', '--console-ready'], ['finish']):
        raise ValueError('Usage: execute.py upgrade --console-ready | finish | status')
    action = sys.argv[1]
    if action == 'upgrade':
        STATE.mkdir(mode=0o700, exist_ok=False)
        with (STATE / 'execute.py').open('x') as stream:
            stream.write(Path(__file__).read_text())
        write(STATE / 'executor-seal.json', {'sha256': sha(STATE / 'execute.py'), 'prep_acceptance_sha256': PREP_SHA})
    else:
        if STATE.is_symlink() or STATE.stat().st_uid != 0: raise ValueError('Private execution directory required')
        if (STATE / 'finish-success.json').exists(): raise ValueError('Maintenance already completed')
    if sha(STATE / 'execute.py') != read(STATE / 'executor-seal.json')['sha256']:
        raise ValueError('Private executor seal differs')
    # Root ownership and an exclusive attempt receipt prevent accidental replay.
    with (STATE / (action + '-attempt.json')).open('x') as stream:
        json.dump({'started_at': datetime.now(timezone.utc).isoformat()}, stream)
    unit = 'homecontrol-host-update-20261103-' + action
    cmd = ['systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--unit=' + unit,
           '--property=Type=exec', '--property=KillMode=control-group', '--property=RuntimeMaxSec=28800',
           '--property=TimeoutStopSec=180', '--property=UMask=0077',
           '/usr/bin/python3', str(STATE / 'execute.py'), '_worker', action]
    result = subprocess.run(cmd)
    if result.returncode:
        say('A felügyelt futás nem zárult sikerrel. Privát állapot: ' + str(STATE))
    raise SystemExit(result.returncode)


if __name__ == '__main__': main()
