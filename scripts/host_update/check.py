"""Read-only integrity and reboot checks for the prepared r22 host maintenance."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

sys.dont_write_bytecode = True

BASE = Path('/srv/docker/homecontrol')
ROOT = BASE / 'maintenance/host-update-20261103'
RELEASE = 'hc-audit-20261103-r22'
KIT = BASE / 'backups/releases' / RELEASE
spec = importlib.util.spec_from_file_location('host_update_checks_plan', Path(__file__).with_name('plan.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def call(args):
    env = {k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','APT_CONFIG')}
    env.update(LC_ALL='C', LANG='C', DOCKER_HOST='unix:///var/run/docker.sock')
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=60, env=env).stdout


def read(path): return json.loads(Path(path).read_text())


def request(path):
    with urllib.request.urlopen('http://127.0.0.1:5000' + path, timeout=10) as response:
        return json.load(response)


def source_fingerprints():
    paths = [Path('/etc/apt/sources.list'), *Path('/etc/apt/sources.list.d').glob('*'),
             *Path('/etc/apt/apt.conf.d').glob('*'), *Path('/etc/apt/preferences.d').glob('*')]
    for root in ('/etc/apt/keyrings', '/etc/apt/trusted.gpg.d', '/usr/share/keyrings'):
        paths.extend(Path(root).glob('*'))
    paths.extend(Path(n) for n in ('/etc/apt/preferences','/etc/apt/trusted.gpg','/etc/apt/apt.conf'))
    return {str(path):p.sha(path) for path in sorted(set(paths)) if path.is_file()}


def snapshot():
    marker = read(BASE / 'infra/access-release.json')
    if marker.get('release') != RELEASE: raise ValueError('Active HC release changed')
    manifest = read(KIT / 'release.json'); accepted = read(KIT / 'evidence/post-live-check.json')
    if not accepted.get('ok') or accepted.get('release') != RELEASE: raise ValueError('Missing final r22 acceptance')
    runtime = Path(marker['runtime'])
    drift = [n for n,h in manifest['source_sha256'].items() if p.sha(runtime / n) != h]
    if drift: raise ValueError('HC runtime source drift')
    rows = json.loads(call(['docker','inspect',*accepted['containers']]))
    for row in rows:
        name = row['Name'].strip('/'); before = accepted['containers'][name]
        if row['Id'] != before['id'] or row['Image'] != before['image']: raise ValueError('HC container identity changed')
        if row['State']['Running'] != before['running']: raise ValueError('HC running state changed')
        if row['State']['Running'] and row['State'].get('Health',{}).get('Status') not in (None,'healthy'):
            raise ValueError('HC component unhealthy')
    expected_running = {row['Name'].strip('/') for row in rows if row['State']['Running']}
    if set(call(['docker','ps','--format','{{.Names}}']).splitlines()) != expected_running:
        raise ValueError('Other running containers require maintenance review')
    for endpoint in ('/health','/health/ready'):
        if request(endpoint).get('ok') is not True: raise ValueError('HC backend not ready')
    policy = request('/api/deployment/status')
    if policy.get('ai_enabled') is not False or policy.get('router_backup_enabled') is not True:
        raise ValueError('HC deployment policy changed')
    units = accepted['scheduled_units']['unit_sha256']
    if any(p.sha(Path('/etc/systemd/system') / n) != h for n,h in units.items()):
        raise ValueError('HC installed unit drift')
    timers = {}
    for name in accepted['active_timers']:
        values = dict(l.split('=',1) for l in call(['systemctl','show',name,
            '--property=ActiveState,UnitFileState,NextElapseUSecRealtime,NextElapseUSecMonotonic','--no-pager']).splitlines() if '=' in l)
        if values.get('ActiveState') != 'active' or values.get('UnitFileState') != 'enabled':
            raise ValueError('HC timer inactive or disabled')
        timers[name] = values
    guards = ('homecontrol-hostops.service','homecontrol-mqtt-access.service')
    for unit in guards:
        if call(['systemctl','show',unit,'--property=ActiveState','--value']).strip() != 'active':
            raise ValueError('HC host guard inactive')
    mounts = {}
    for name in ('backups','backups/releases','backups/ai-control','backups/ai-backup.lock','backups/homecontrol-backup.lock'):
        values = json.loads(call(['findmnt','--json','--target',str(BASE/name),'--output','TARGET,FSTYPE,UUID,FSROOT']))['filesystems']
        normalized = {json.dumps(v,sort_keys=True) for v in values}
        if len(normalized) != 1: raise ValueError('Ambiguous HC backup mount')
        mounts[name] = json.loads(normalized.pop())
        if mounts[name].get('target') != str(BASE/name) or not mounts[name].get('uuid'):
            raise ValueError('Expected HC bind mount missing')
    root_device = call(['findmnt','--noheadings','--output','UUID','--target','/']).strip()
    os_release = {k:v.strip('"') for l in Path('/etc/os-release').read_text().splitlines() if '=' in l for k,v in [l.split('=',1)]}
    if os_release.get('ID') != 'ubuntu' or os_release.get('VERSION_ID') != '22.04': raise ValueError('Host OS release changed')
    return {'captured_at':datetime.now(timezone.utc).isoformat(),'release':RELEASE,'os':os_release.get('PRETTY_NAME'),
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'kernel':call(['uname','-r']).strip(),
        'next_kernel':Path('/boot/vmlinuz').resolve().name.removeprefix('vmlinuz-'),
        'root_uuid':root_device,'containers':accepted['containers'],'runtime_source_count':len(manifest['source_sha256']),
        'unit_sha256':units,'timers':timers,'mounts':mounts,'ai_enabled':False,'router_backup_enabled':True,
        'compose_sha256':p.sha(BASE/'infra/docker-compose.yml'),'apt_configuration_sha256':source_fingerprints(),
        'dpkg_status_sha256':p.sha('/var/lib/dpkg/status'),'holds':call(['apt-mark','showhold']).splitlines(),
        'dpkg_audit':call(['dpkg','--audit']).strip()}


def verify_package():
    acceptance = read(ROOT / 'acceptance.json')
    if not acceptance.get('ok'): raise ValueError('Preparation not accepted')
    for name, expected in acceptance['sha256'].items():
        path = ROOT / name
        if any(v.is_symlink() for v in (path,*path.parents)) or p.sha(path) != expected:
            raise ValueError('Prepared artifact changed')
    plan = read(ROOT / 'plan.json')
    for record in [r['catalog'] for r in plan['transactions']] + plan['rollback_packages']:
        p.verify_deb(ROOT / record['local_file'], record)
    return plan


def validate_reboot(current, baseline, *, require_reboot=True):
    if require_reboot:
        if current['boot_id'] == baseline['boot_id']: raise ValueError('Expected reboot has not occurred')
        if current['kernel'] != baseline['next_kernel']: raise ValueError('Expected kernel is not running')
    if current['mounts'] != baseline['mounts'] or current['root_uuid'] != baseline['root_uuid']:
        raise ValueError('Post-boot filesystem layout differs')
    if current['dpkg_audit']: raise ValueError('dpkg needs reconciliation')


def verify_runtime_schedules():
    # Reuse the exact r22 checker and its already accepted oneshot-wait adapter.
    # apply=False in the frozen schedule generator performs no installation.
    if os.geteuid() != 0: raise PermissionError('Run the full postcheck with local sudo')
    source = KIT / 'source/scripts/audit_release'
    spec = importlib.util.spec_from_file_location('host_update_readonly_activation', source / 'activate.py')
    activation = importlib.util.module_from_spec(spec); spec.loader.exec_module(activation)
    core = activation.router.core; core.verify()
    sys.path.insert(0, str(source))
    import schedules
    if Path(schedules.__file__).resolve() != source / 'schedules.py': raise ValueError('Unexpected schedule checker')
    spec = importlib.util.spec_from_file_location('host_update_health_settle', Path(__file__).with_name('timer_settle.py'))
    settle = importlib.util.module_from_spec(spec); spec.loader.exec_module(settle)
    return settle.check(core, schedules.check_schedules, schedules.schedule_plan(core))


def main(action):
    if action == 'baseline':
        result = snapshot()
        path = ROOT / 'host-baseline.json'
        if path.exists(): raise ValueError('Host baseline already captured')
        path.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'ok':True,'release':result['release'],'runtime_source_count':result['runtime_source_count'],'mounts':len(result['mounts']),'kernel':result['kernel'],'next_kernel':result['next_kernel']},indent=2)); return
    plan = verify_package(); baseline = read(ROOT / 'host-baseline.json')
    if action == 'verify':
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(plan['prepared_at'])).total_seconds()
        if not 0 <= age <= 86400: raise ValueError('Prepared catalog is older than 24 hours; refresh plan')
        if p.sha('/var/lib/dpkg/status') != plan['package_database_sha256']: raise ValueError('Host package state changed; refresh plan')
        if source_fingerprints() != baseline['apt_configuration_sha256']: raise ValueError('Host APT configuration changed')
        simulation = p.parse_simulation(call(['apt-get','-c',str(ROOT/'apt/prepare.conf'),'--simulate','--with-new-pkgs','upgrade']))
        expected = [{k:v for k,v in row.items() if k != 'catalog'} for row in plan['transactions']]
        if simulation != expected: raise ValueError('APT simulation differs from reviewed plan')
        print(json.dumps({'ok':True,'packages_verified':len(plan['transactions']),'rollback_packages_verified':len(plan['rollback_packages']),'packages_installed':False})); return
    if action not in ('before-reboot','postcheck'): raise ValueError('Unknown action')
    current = snapshot()
    validate_reboot(current, baseline, require_reboot=action=='postcheck')
    for row in plan['transactions']:
        version = call(['dpkg-query','-W','-f=${Version}',row['package']]).strip()
        if version != row['candidate']: raise ValueError('Installed package differs from reviewed plan')
    schedules = verify_runtime_schedules()
    print(json.dumps({'ok':True,'release':RELEASE,'reboot_verified':action=='postcheck','kernel':current['kernel'],'containers_verified':len(current['containers']),'backup_mounts_verified':len(current['mounts']),'package_versions_verified':len(plan['transactions']),'timers_verified':len(schedules['timers']),'health_service_acceptance':schedules['health_service_acceptance'],'note':'This is a software postcheck; a fresh backup/restore and device verification remain separate acceptance steps.'},indent=2))


if __name__ == '__main__':
    try: main(sys.argv[1] if len(sys.argv)==2 else 'verify')
    except Exception as error:
        print(json.dumps({'ok':False,'condition':str(error) if type(error) is ValueError else type(error).__name__}),file=sys.stderr)
        raise SystemExit(1)
