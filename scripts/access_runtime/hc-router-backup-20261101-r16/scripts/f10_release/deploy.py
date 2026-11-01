"""Application-only r13 cutover. Root, sealed inputs, backup and automatic rollback.

No root fallback or container-based host file access. Read-only checks can run as
the operator; secret preparation and systemd/canonical changes require real sudo.
"""
import argparse
import fcntl
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

sys.dont_write_bytecode=True

BASE=Path('/srv/docker/homecontrol')
CANONICAL_BASE=Path('/srv/docker/homecontrol')
NAME='hc-router-backup-20261101-r16'
OLD='hc-router-backup-20261101-r15'
KIT=BASE/'backups/releases'/NAME
RUNTIME=BASE/'scripts/access_runtime'/NAME
PRIVATE=BASE/'infra/ssh'/NAME
OLD_RUNTIME=BASE/'scripts/access_runtime'/OLD
OLD_PRIVATE=BASE/'infra/ssh'/OLD
STATE=KIT/'private/transition'
UNIT_ROOT=Path('/etc/systemd/system')
BUSY_UNITS=('homecontrol-backup.service','homecontrol-ai-weekly-backup.service',
 'homecontrol-full-ai-backup-request.service','homecontrol-restic-check.service',
 'homecontrol-log-maintenance.service','homecontrol-backup-apply.service')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def call(args, *, allowed=(0,), timeout=180, extra_env=None, **kwargs):
    env={k:v for k,v in os.environ.items() if k not in ('DOCKER_CONTEXT','DOCKER_HOST','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    env.update(extra_env or {})
    env['DOCKER_HOST']='unix:///var/run/docker.sock'
    result=subprocess.run(args,capture_output=True,env=env,timeout=timeout,**kwargs)
    if result.returncode not in allowed:raise RuntimeError('Release operation failed: '+str(args[0]))
    return result


def platform():
    sys.path.insert(0,str(KIT/'source/scripts/access_release'))
    import common
    return common


def load():return json.loads((KIT/'release.json').read_text())


def locked(stack):
    # The reviewed lock adapter lives in access_release/install.py, not common.py.
    # Import explicitly before a cutover can stop any application.
    platform()
    from install import locked as acquire
    return acquire(stack)


def runtime_adapters():
    p=platform()
    import install
    import climate_handover
    for module,names in ((p,('snapshot','restore_snapshot','units','no_symlinks','write_json')),
                         (install,('locked','permissions','install_units')),
                         (climate_handover,('reconcile',))):
        if any(not callable(getattr(module,name,None)) for name in names):
            raise ValueError('Required release adapter unavailable before cutover')
    p.units(KIT/'source')


def compose(path):
    return ['docker','compose','-p','homecontrol','--profile','ha-growatt','-f',str(path)]


def container(service):
    return 'homecontrol-'+('ingest' if service=='hc_ingest' else service.removeprefix('homecontrol-'))


def verify(*, allow_cloud_pending=False):
    m=load();p=platform()
    runtime_adapters()
    if m['release']!=NAME:raise ValueError('Wrong release')
    if not m.get('ready_for_root_deploy') and not allow_cloud_pending:raise ValueError('Release acceptance is incomplete')
    for name,sha in m['source_sha256'].items():
        path=KIT/'source'/name;p.no_symlinks(path)
        if digest(path)!=sha:raise ValueError('Sealed source changed: '+name)
    acceptance=KIT/'evidence/acceptance.json'
    if digest(acceptance)!=m['acceptance_sha256']:raise ValueError('Acceptance report changed')
    report=json.loads(acceptance.read_text())
    if not report.get('ok'):
        if not (allow_cloud_pending and report.get('pending')==['authenticated Xiaomi cloud smoke under local sudo']):
            raise ValueError('Acceptance failed')
    for name,sha in report['evidence_sha256'].items():
        path=KIT/'evidence'/name;p.no_symlinks(path)
        if digest(path)!=sha:raise ValueError('Acceptance evidence changed: '+name)
    for image in m['images'].values():
        info=json.loads(call(['docker','image','inspect',image]).stdout)[0]
        if info['Id']!=image:raise ValueError('Pinned image missing')
    archive=KIT/'private/access-images.tar.gz'
    if digest(archive)!=m['offline_image_archive_sha256']:raise ValueError('Offline image archive changed')
    return m


def phase(name):
    status={'phase':name,'timestamp':time.time()}
    platform().write_json(KIT/'private/progress.json',status)
    platform().write_json(KIT/'deployment-status.json',status,0o644)


def active(unit):return call(['systemctl','is-active','--quiet',unit],allowed=(0,3,4)).returncode==0


def idle():
    if any(active(n) for n in BUSY_UNITS):raise ValueError('Active backup/restore operation')
    for path in Path('/var/lib/homecontrol-hostops/jobs').glob('*.json'):
        if json.loads(path.read_text()).get('state') in ('queued','running'):
            raise ValueError('Active host job; reconcile first')


def request(path):
    with urllib.request.urlopen('http://127.0.0.1:5000'+path,timeout=5) as response:
        return json.load(response)


def guard_runtime(m):
    marker=json.loads((BASE/'infra/access-release.json').read_text())
    if marker['release']!=OLD:raise ValueError('Active release is not the reviewed r10 baseline')
    if digest(BASE/'infra/docker-compose.yml')!=m['previous_compose_sha256']:
        raise ValueError('Active Compose changed')
    for name,expected in m['baseline'].items():
        row=json.loads(call(['docker','inspect',name]).stdout)[0]
        if row['Id']!=expected['id'] or row['Image']!=expected['image']:
            raise ValueError('Container changed since preparation: '+name)
    for unit in ('homecontrol-hostops.service','homecontrol-mqtt-access.service'):
        if not active(unit):raise ValueError('Existing hostops/MQTT guard is not active')
    if request('/health').get('ok') is not True:raise ValueError('Existing backend is not ready')
    robot=request('/api/xiaomi-x10/state')
    if str(robot.get('robot_state')) not in ('6','13'):
        raise ValueError('Robot must be idle or charging for the bridge handover')
    # No actuation: fail closed if an irrigation session is still running.
    command=['docker','exec','-i','homecontrol-postgres','sh','-c',
      'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    sql="""SELECT (SELECT count(*) FROM hc.irrigation_manual_session
        WHERE status IN ('starting','running','stop_failed')) +
        (SELECT count(*) FROM hc.irrigation_solar_pump_run WHERE status='running');"""
    if call(command,input=sql.encode()).stdout.strip()!=b'0':raise ValueError('Active irrigation session')
    idle()


def secret_archive_name(file):
    """Keep the restore allowlist fixed, including in synthetic filesystem tests."""
    file=Path(file)
    if file.is_relative_to(BASE):return CANONICAL_BASE/file.relative_to(BASE)
    if file.is_relative_to('/etc/homecontrol'):return file
    raise ValueError('Secret path outside restore allowlist')


def encrypted_bundle(runtime):
    """Refresh the existing encrypted bundle using root filesystem access only."""
    p=platform();identity=BASE/'infra/ssh/homecontrol-secrets-age-key.txt'
    output=KIT/'private/homecontrol-secrets-r13.tar.gz.age'
    sys.path.insert(0,str(KIT/'source/scripts'))
    from restore_archive import secrets as extract
    with tempfile.TemporaryDirectory(prefix='.r13-secrets-',dir=KIT/'private') as directory:
        work=Path(directory);plain=work/'base.tar.gz'
        plain.write_bytes(call(['age','-d','-i',str(identity),str(BASE/'secrets/homecontrol-secrets-latest.tar.gz.age')]).stdout)
        root=work/'root';extract(plain,root)
        paths=[]
        for line in (BASE/'secrets/manifest.txt').read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                path=Path(line.strip());paths.append(path if path.is_absolute() else BASE/path)
        paths.extend((BASE/'apps/xiaomi-x10/x10_maps').glob('xiaomi_cloud_auth*.json'))
        router = globals().get('ROUTER_SETTINGS')
        if router:
            paths.extend(Path(router[key]) for key in ('router_rclone_config','restic_password_file'))
        for source in paths:
            if source==identity:continue
            files=[source] if source.is_file() else list(source.rglob('*')) if source.is_dir() else []
            for file in files:
                if file==identity or not file.is_file() or 'images' in file.parts:continue
                p.no_symlinks(file)
                dest=root/str(secret_archive_name(file)).lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(file,dest);dest.chmod(0o600)
        if globals().get('ROUTER_SETTINGS'):
            target = root/'srv/docker/homecontrol/backups/backup_settings.json'
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(ROUTER_SETTINGS)+'\n');target.chmod(0o600)
        for file in runtime.rglob('*'):
            if not file.is_file() or file.is_relative_to(runtime/'images'):continue
            dest=root/str(secret_archive_name(PRIVATE)).lstrip('/')/file.relative_to(runtime)
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,dest);dest.chmod(0o600)
        files=[f for f in root.rglob('*') if f.is_file() and not f.name.startswith('SECRETS_BUNDLE_')]
        (root/'SECRETS_BUNDLE_CONTENTS.txt').write_text('\n'.join('/'+str(f.relative_to(root)) for f in sorted(files))+'\n')
        (root/'SECRETS_BUNDLE_METADATA.txt').write_text('release='+NAME+'\n')
        packed=work/'new.tar.gz'
        with tarfile.open(packed,'w:gz') as tar:tar.add(root,arcname='.')
        recipient=(BASE/'secrets/age-recipient.txt').read_text().strip()
        call(['age','-r',recipient,'-o',str(output)],input=packed.read_bytes())
        output.chmod(0o600)
        decoded=work/'check.tar.gz';decoded.write_bytes(call(['age','-d','-i',str(identity),str(output)]).stdout)
        check=work/'check';extract(decoded,check)
        if any(digest(f)!=digest(check/f.relative_to(root)) for f in files):raise ValueError('Encrypted secret roundtrip failed')
        p.write_json(KIT/'private/secret-receipt.json',{'roundtrip_verified':True,'files':len(files),'sha256':digest(output)})


def prepare_private(m):
    p=platform();runtime=KIT/'private/runtime'
    if runtime.exists():raise ValueError('Private staging already exists; reconcile earlier attempt')
    runtime.mkdir(mode=0o700)
    for name in ('compose-env','mqtt'):
        shutil.copytree(OLD_PRIVATE/name,runtime/name)
    shutil.copyfile(OLD_PRIVATE/'network-policy.json',runtime/'network-policy.json')
    policy=json.loads((runtime/'network-policy.json').read_text())
    if policy.get('esp_ip')!='192.168.1.179' or policy.get('esp_confirmed') is not True:
        raise ValueError('The approved ESP exception changed')
    for path in (runtime/'compose-env').glob('*.env'):
        data=path.read_bytes().replace(str(OLD_RUNTIME).encode(),str(RUNTIME).encode()).replace(str(OLD_PRIVATE).encode(),str(PRIVATE).encode())
        path.write_bytes(data);path.chmod(0o600)
    images=runtime/'images';images.mkdir()
    shutil.copyfile(KIT/'private/access-images.tar.gz',images/'access-images.tar.gz')
    p.write_json(images/'manifest.json',{'archive':'access-images.tar.gz','sha256':m['offline_image_archive_sha256'],'images':m['recovery_images']})
    encrypted_bundle(runtime)


def fresh_backup():
    p=platform()
    before={path.name for path in (BASE/'backups').glob('homecontrol_*.tar.gz.complete.json')}
    call(['python3',str(OLD_RUNTIME/'scripts/hostops/backup_runner.py'),'--mode','local'],timeout=900)
    sys.path.insert(0,str(KIT/'source/infra/backend'))
    from backup_protocol import verify_archive
    files=[f for f in (BASE/'backups').glob('homecontrol_*.tar.gz.complete.json') if f.name not in before]
    if len(files)!=1:raise ValueError('One new verified local backup is required')
    receipt=json.loads(files[0].read_text());archive=BASE/'backups'/receipt['name']
    checked=verify_archive(archive)
    if not receipt.get('completed') or checked['sha256']!=receipt['sha256']:raise ValueError('Fresh backup verification failed')
    p.write_json(KIT/'private/pre-backup.json',{'name':archive.name,**checked})


def target_files():
    p=platform()
    targets=[BASE/name for name in ('infra/docker-compose.yml','infra/access-release.json','scripts/backup_runner.py',
      'scripts/install_restore_host.py','scripts/restore_runtime.py','scripts/bootstrap_restore_v0_1.sh',
      'secrets/manifest.txt','secrets/homecontrol-secrets-latest.tar.gz.age','secrets/homecontrol-secrets-latest.tar.gz.age.sha256')]
    return targets+[UNIT_ROOT/name for name in p.units(KIT/'source')]


def atomic_copy(source,target):
    p=platform();p.no_symlinks(target);target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_name('.'+target.name+'.r13-'+uuid.uuid4().hex)
    shutil.copyfile(source,tmp);tmp.chmod(0o755 if target.suffix in ('.py','.sh') else 0o600 if '.age' in target.name and not target.name.endswith('sha256') else 0o644)
    with tmp.open('rb') as handle:os.fsync(handle.fileno())
    os.replace(tmp,target)


def install_files(m):
    p=platform()
    if RUNTIME.exists() or PRIVATE.exists():raise ValueError('New runtime/private destination already exists')
    p.no_symlinks(RUNTIME);p.no_symlinks(PRIVATE)
    shutil.copytree(KIT/'source',RUNTIME);shutil.copytree(KIT/'private/runtime',PRIVATE);PRIVATE.chmod(0o700)
    for target,source in {
      BASE/'infra/docker-compose.yml':RUNTIME/'runtime.compose.json',
      BASE/'scripts/backup_runner.py':RUNTIME/'canonical_backup_runner.py',
      **{BASE/'scripts'/name:RUNTIME/'scripts'/name for name in ('install_restore_host.py','restore_runtime.py','bootstrap_restore_v0_1.sh')}
    }.items():atomic_copy(source,target)
    p.write_json(BASE/'infra/access-release.json',{'release':NAME,'runtime':str(RUNTIME),'private':str(PRIVATE),
        'image_archive_sha256':m['offline_image_archive_sha256']},0o644)
    manifest=BASE/'secrets/manifest.txt';text=manifest.read_text()
    for name in ('compose-env','mqtt','network-policy.json'):
        if str(PRIVATE/name) not in text:text=text.rstrip()+'\n'+str(PRIVATE/name)+'\n'
    manifest.write_text(text)
    atomic_copy(KIT/'private/homecontrol-secrets-r13.tar.gz.age',BASE/'secrets/homecontrol-secrets-latest.tar.gz.age')
    checksum=BASE/'secrets/homecontrol-secrets-latest.tar.gz.age.sha256'
    checksum.write_text(digest(BASE/'secrets/homecontrol-secrets-latest.tar.gz.age')+'  homecontrol-secrets-latest.tar.gz.age\n')
    sys.path.insert(0,str(RUNTIME/'scripts/access_release'))
    import install
    install.permissions();install.install_units()


def wait_ready(m, *, previous=False):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        try:
            path='/health' if previous else '/health/ready'
            if request(path).get('ok') is not True:raise ValueError('Not ready')
            for service,image in m['images'].items():
                row=json.loads(call(['docker','inspect',container(service)],timeout=10).stdout)[0]
                expected=m['baseline'][container(service)]['image'] if previous else image
                if row['Image']!=expected or not row['State']['Running']:raise ValueError('Wrong application image')
                if not previous and row['State'].get('Health',{}).get('Status')!='healthy':raise ValueError('Application health pending')
                if service=='backend':
                    sys.path.insert(0,str(KIT/'source/scripts/hostops'))
                    from installation_plan import validate_backend
                    if validate_backend(row):raise ValueError('Backend permission contract changed')
            changed={container(s) for s in m['changed_services']}
            for name,expected in m['baseline'].items():
                if name in changed:continue
                row=json.loads(call(['docker','inspect',name],timeout=10).stdout)[0]
                if row['Id']!=expected['id'] or row['Image']!=expected['image']:
                    raise ValueError('Unchanged platform container was replaced: '+name)
            call(['docker','exec','homecontrol-backend','python','-B','-c',
              'from host_operations_client import HostOperationsClient; assert HostOperationsClient().call("containers",timeout=5)'],timeout=8)
            return
        except (OSError,ValueError,RuntimeError):time.sleep(1)
    raise RuntimeError('Application readiness failed')


def reconcile(reason):
    from climate_handover import reconcile as handover
    return handover(KIT/'private/handover'/uuid.uuid4().hex,reason)


def rollback(m):
    p=platform()
    marker=json.loads((BASE/'infra/access-release.json').read_text())
    if marker.get('release') not in (NAME,OLD):raise ValueError('A later release blocks this rollback')
    state=json.loads((STATE/'transition.json').read_text())
    if state.get('release')!=NAME:raise ValueError('Transition release mismatch')
    if (STATE/'result.json').exists() and json.loads((STATE/'result.json').read_text()).get('state')=='rolled_back':
        if digest(BASE/'infra/docker-compose.yml')!=m['previous_compose_sha256']:
            raise ValueError('Previously rolled-back Compose has changed')
        wait_ready(m,previous=True)
        return
    phase('rollback')
    for unit in state['active_timers']:
        if active(unit):call(['systemctl','stop',unit])
    idle()
    call(['docker','stop','--time','30',*[container(s) for s in m['changed_services']]],allowed=(0,1))
    call(['systemctl','stop','homecontrol-hostops.service'])
    with ExitStack() as stack:
        locked(stack);reconcile('rollback');p.restore_snapshot(STATE)
    call(['systemctl','daemon-reload']);call(['systemctl','start','homecontrol-hostops.service'])
    call(compose(BASE/'infra/docker-compose.yml')+['up','-d','--no-deps','--no-build','--pull','never',*m['changed_services']])
    wait_ready(m,previous=True)
    for unit,wanted in state['active_timers'].items():
        if wanted:call(['systemctl','start',unit])
    p.write_json(STATE/'result.json',{'state':'rolled_back','success':True})
    phase('previous_release_restored')


def switch(context):
    """Small transaction surface for fault-injection tests, including partial stops."""
    stopping=False
    try:
        context.quiesce()
        stopping=True
        context.stop();context.install();context.start();context.verify();context.resume()
    except BaseException:
        if stopping:context.rollback()
        else:context.resume()
        raise


class Cutover:
    def __init__(self,m,timers):self.m,self.timers=m,timers
    def quiesce(self):
        phase('quiesce')
        for unit,wanted in self.timers.items():
            if wanted:call(['systemctl','stop',unit])
        idle()
    def stop(self):
        phase('stop_applications')
        call(['docker','stop','--time','30','homecontrol-backend'])
        call(['docker','stop','--time','30',*[container(s) for s in self.m['changed_services'] if s!='backend']])
        call(['systemctl','stop','homecontrol-hostops.service'])
    def install(self):
        phase('install')
        with ExitStack() as stack:
            locked(stack);reconcile('deploy');install_files(self.m)
    def start(self):
        phase('start_applications')
        call(['systemctl','start','homecontrol-hostops.service'])
        call(compose(BASE/'infra/docker-compose.yml')+['up','-d','--no-deps','--no-build','--pull','never',*self.m['changed_services']])
    def verify(self):
        phase('readiness');wait_ready(self.m)
    def resume(self):
        for unit,wanted in self.timers.items():
            if wanted:call(['systemctl','start',unit])
    def rollback(self):rollback(self.m)


def deploy():
    m=verify();guard_runtime(m)
    p=platform()
    if STATE.exists():raise ValueError('Existing transition; inspect or rollback explicitly')
    if RUNTIME.exists() or PRIVATE.exists():raise ValueError('Unexpected existing release destination')
    # Exercise the actual root lock adapter while every application still runs.
    # An import/permission/contended-lock error must not require a rollback.
    phase('preflight_common_locks')
    with ExitStack() as stack:locked(stack)
    phase('prepare_private');prepare_private(m)
    phase('fresh_backup');fresh_backup();guard_runtime(m)
    timers={unit:active(unit) for unit in p.QUIESCE}
    p.snapshot(target_files(),STATE)
    p.write_json(STATE/'transition.json',{'release':NAME,'state':'starting','active_timers':timers})
    try:switch(Cutover(m,timers))
    except BaseException:
        if not (STATE/'result.json').exists():p.write_json(STATE/'result.json',{'state':'failed_reconcile_required','success':False})
        raise
    p.write_json(STATE/'result.json',{'state':'deployed_requires_supervised_acceptance','success':True})
    p.write_json(PRIVATE/'installed.json',{'release':NAME,'state':'running_requires_supervised_acceptance','transition':str(STATE)})
    phase('deployed_requires_supervised_acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('check','deploy','rollback'))
    args=parser.parse_args()
    try:
        if args.action=='check':verify()
        else:
            if os.geteuid()!=0:raise PermissionError('Run the reviewed command with sudo in the local terminal')
            def terminate(signum,frame):raise InterruptedError('Operator terminated the cutover')
            signal.signal(signal.SIGTERM,terminate)
            platform().no_symlinks(KIT/'private/operator.lock')
            with (KIT/'private/operator.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if args.action=='deploy':deploy()
                else:
                    m=verify()
                    if not (STATE/'transition.json').exists():raise ValueError('No recorded transition')
                    rollback(m)
        print(json.dumps({'action':args.action,'success':True}))
    except BaseException as exc:
        if isinstance(exc,KeyboardInterrupt):raise
        if os.geteuid()==0:
            platform().write_json(KIT/'private/error.json',{'error_type':type(exc).__name__,
                'detail':str(exc),'time':time.time()})
        raise SystemExit('r13 stopped ('+type(exc).__name__+'); inspect private/progress.json and private/error.json; no secrets printed')
