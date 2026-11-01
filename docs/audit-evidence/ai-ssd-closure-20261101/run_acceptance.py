#!/usr/bin/env python3
"""Guarded guest-only fresh/repeated/reboot/offline-target acceptance."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import lab_vm

OUT = Path(__file__).resolve().parent
report = {'ok': False, 'scope': 'real r15 archive and external Git plus explicit recovery corrections',
          'started_at': datetime.now(timezone.utc).isoformat(), 'remote_write_commands': 0,
          'production_restore': False, 'ai_enabled': False}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def phase(name):
    report['phase'] = name
    save('acceptance-progress.json', report)
    print(name, flush=True)


def read(name):
    return json.loads(lab_vm.ssh(['sudo', 'cat', '/lab/' + name + '.json'], capture_output=True, text=True).stdout)


def program(code):
    return lab_vm.ssh(['sudo', 'python3'], input=code, text=True, capture_output=True).stdout


def run(mode, expected=True):
    lab_vm.ssh(['sudo', 'systemd-run', '--unit=hc-lab-' + mode + '-restore',
                '/usr/bin/python3', '/lab/run_restore.py', mode], capture_output=True, text=True)
    deadline = time.monotonic() + 10800
    while time.monotonic() < deadline:
        try:
            result = read(mode)
            save(mode + '-restore.json', result)
            if result['ok'] != expected:
                raise RuntimeError('Unexpected guest restore result: ' + mode)
            return result
        except subprocess.CalledProcessError:
            state = lab_vm.ssh(['sudo', 'systemctl', 'show', 'hc-lab-' + mode + '-restore',
                                '--property=ActiveState,ExecMainStatus'], capture_output=True, text=True).stdout
            if 'ActiveState=failed' in state:
                raise RuntimeError('Guest restore service failed before writing a receipt')
            time.sleep(5)
    raise TimeoutError('Guest restore acceptance timed out')


def probe(name):
    for attempt in range(12):
        try:
            lab_vm.ssh(['sudo', 'python3', '/lab/probe_restored.py', name], capture_output=True, text=True)
            break
        except subprocess.CalledProcessError:
            if attempt == 11:
                raise
            time.sleep(5)
    value = read(name)
    save(name + '.json', value)
    return value


def fingerprint():
    return json.loads(program('''import hashlib,json,subprocess
from pathlib import Path
base=Path('/srv/docker/homecontrol')
installed=json.loads((base/'backups/f6-installed.json').read_text())
paths=[base/'infra/docker-compose.yml',base/'infra/access-release.json',base/'scripts/bootstrap_restore_v0_1.sh']
paths += [Path('/etc/systemd/system')/name for name in installed['units']]
print(json.dumps({'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'database':json.loads(subprocess.check_output(['docker','inspect','homecontrol-postgres'],text=True))[0]['Id']}))
'''))


try:
    phase('fresh_restore')
    for name in ('run_restore.py', 'probe_restored.py'):
        lab_vm.ssh(['sudo', 'tee', '/lab/' + name], input=(OUT / name).read_text(),
                   text=True, stdout=subprocess.DEVNULL)
    report['fresh'] = run('fresh')
    phase('fresh_host_probe')
    fresh = probe('fresh-probe')
    report['selected_dump_sha256'] = fresh['selected_dump_sha256']
    phase('unavailable_repository')
    before = fingerprint()
    lab_vm.ssh(['sudo', 'systemctl', 'stop', 'hc-lab-ftp.service'], capture_output=True, text=True)
    try:
        negative = run('unavailable', expected=False)
    finally:
        lab_vm.ssh(['sudo', 'systemctl', 'start', 'hc-lab-ftp.service'], capture_output=True, text=True)
    assert negative['returncode'] != 0 and before == fingerprint()
    save('unavailable-repository.json', {'ok': True, 'nonzero_exit': True,
         'canonical_files_and_units_unchanged': True, 'database_container_unchanged': True})
    phase('repeated_restore')
    program('''import shutil,sys
from pathlib import Path
sys.path.insert(0,'/lab')
from setup_guest import guard
guard()
p=Path('/lab/restore/restic');assert p.is_dir() and not p.is_symlink()
shutil.rmtree(p);p.mkdir(mode=0o700);(p/'old-stage-canary').write_text('previous staging must be isolated')
''')
    report['repeat'] = run('repeat')
    repeated = probe('repeat-probe')
    assert fresh['unit_hashes'] == repeated['unit_hashes']
    assert fresh['selected_dump_sha256'] == repeated['selected_dump_sha256']
    phase('guest_reboot')
    boot = lab_vm.ssh(['cat', '/proc/sys/kernel/random/boot_id'], capture_output=True, text=True).stdout.strip()
    try:
        lab_vm.ssh(['sudo', 'systemctl', 'reboot'], capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        if error.returncode != 255:
            raise
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        time.sleep(5)
        try:
            current = lab_vm.ssh(['cat', '/proc/sys/kernel/random/boot_id'], capture_output=True, text=True).stdout.strip()
            if current != boot:
                break
        except subprocess.CalledProcessError:
            pass
    else:
        raise TimeoutError('Guest reboot did not complete')
    phase('post_reboot_probe')
    rebooted = probe('post-reboot-probe')
    assert rebooted['unit_hashes'] == fresh['unit_hashes']
    report.update(ok=True, reboot_verified=True, new_boot_id=True,
                  repeated_unit_bytes_identical=True, unavailable_repository_preserves_live_state=True,
                  offline_homeassistant_verified=True, root_ipc_verified=True, five_timers_verified=True,
                  phase='completed')
except Exception as error:
    report['error_type'] = type(error).__name__
    print('Acceptance stopped:', report['phase'], type(error).__name__, flush=True)
finally:
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save('vm-acceptance.json', report)
    save('acceptance-progress.json', report)
raise SystemExit(0 if report['ok'] else 1)
