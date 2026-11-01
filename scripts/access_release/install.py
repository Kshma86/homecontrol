#!/usr/bin/env python3
"""Root cutover/rollback for the sealed access kit. No action without a subcommand."""
import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

from common import BASE, NAME, PRIVATE, RUNTIME, SERVICES, QUIESCE, cancel_intent, digest, no_symlinks, restore_snapshot, snapshot, units, write_json
from network import execute as firewall


def call(args, allowed=(0,)):
    env={k:v for k,v in os.environ.items() if k not in ('DOCKER_CONTEXT','DOCKER_HOST','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    env['DOCKER_HOST']='unix:///var/run/docker.sock'
    result=subprocess.run(args,capture_output=True,text=True,env=env)
    if result.returncode not in allowed:raise RuntimeError('Access operation failed: '+args[0])
    return result


def verify(kit):
    kit=Path(kit);m=json.loads((kit/'release.json').read_text())
    if m['release']!=NAME or not m.get('source_sha256') or not m.get('images'):raise ValueError('Unsealed release')
    if any(n in m.get('scope',[]) for n in ('HC-35','HC-36')) and not all(n in m['images'] for n in ('backend','frontend')):
        raise ValueError('HC-35/36 requires a matching backend and frontend image')
    if 'HC-35' in m.get('scope',[]):
        binding=json.loads((kit/'source/binding-release.json').read_text())
        if any(binding[n+'_image']!=m['images'][n] for n in ('backend','frontend')):
            raise ValueError('Binding release metadata differs from the image pair')
    for directory,key in (('source','source_sha256'),('private','private_sha256')):
        for name,expected in m[key].items():
            path=kit/directory/name;no_symlinks(path)
            if digest(path)!=expected:raise ValueError('Release integrity failed: '+name)
    images=kit/'private/runtime/images/access-images.tar.gz'
    if digest(images)!=m['offline_image_archive_sha256']:raise ValueError('Offline image archive changed')
    return m


def locked(stack):
    handles=[]
    for name in ('ai-backup.lock','homecontrol-backup.lock'):
        path=BASE/'backups'/name;no_symlinks(path)
        if not path.is_file():raise ValueError('Existing common lock required; no replacement allowed')
        fd=stack.enter_context(path.open('a'));fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);handles.append(fd)
    return handles


def permissions():
    for relative in ('backups/ai-control','infra/private'):
        path=BASE/relative;no_symlinks(path);path.mkdir(exist_ok=True);os.chown(path,10001,10001);path.chmod(0o700)
        for file in path.iterdir():
            if file.is_symlink() or not file.is_file():raise ValueError('Unexpected mutable data entry')
            os.chown(file,10001,10001);file.chmod(0o600)
    for name in ('ai-backup.lock','homecontrol-backup.lock'):
        path=BASE/'backups'/name;before=path.stat().st_ino
        os.chown(path,0,10001);path.chmod(0o660)
        if path.stat().st_ino!=before:raise RuntimeError('Common lock inode changed')
    # Only broker config is readable by the Mosquitto runtime UID. Other roles'
    # environment/secret files are outside that bind mount.
    for path in (PRIVATE/'mqtt/broker').rglob('*'):
        no_symlinks(path);os.chown(path,1883,1883);path.chmod(0o700 if path.is_dir() else 0o600)
    os.chown(PRIVATE/'mqtt/broker',1883,1883);(PRIVATE/'mqtt/broker').chmod(0o700)
    password=PRIVATE/'mqtt/credentials/backend.password';os.chown(password,10001,10001);password.chmod(0o400)


def transfer_state(source,target,reason):
    no_symlinks(source);no_symlinks(target)
    value=json.loads(source.read_text()) if source.exists() else {'version':1,'generation':None,'intent':None}
    write_json(target,cancel_intent(value,reason))


def install_files(kit,approval):
    m=verify(kit);kit=Path(kit)
    policy=json.loads((kit/'private/runtime/network-policy.json').read_text())
    if policy.get('esp_confirmed') is not True or policy.get('esp_ip')!=approval['esp_ip']:
        raise ValueError('Finalize and seal the ESP policy and encrypted bundle before deployment')
    if RUNTIME.exists() or PRIVATE.exists():raise ValueError('Runtime/private target already exists; reconcile the recorded transition')
    for p in (RUNTIME.parent,PRIVATE.parent):no_symlinks(p)
    shutil.copytree(kit/'source',RUNTIME);shutil.copytree(kit/'private/runtime',PRIVATE)
    PRIVATE.chmod(0o700)
    write_json(PRIVATE/'network-policy.json',dict(esp_ip=approval['esp_ip'],broker_ip=m['network']['broker_ip'],
        docker_subnet=m['network']['subnet'],dashboard_ip='192.168.1.89',mode='authenticated',owned_chain=False,esp_confirmed=True))
    transfer_state(BASE/'backups/ai-power-state.json',BASE/'backups/ai-control/ai-power-state.json','access-release handover')
    # Old consumers must not resurrect the pre-handover intent after an early failure.
    write_json(BASE/'backups/ai-power-state.json',json.loads((BASE/'backups/ai-control/ai-power-state.json').read_text()))
    permissions()
    replacements={BASE/'infra/docker-compose.yml':RUNTIME/'runtime.compose.json',
        BASE/'scripts/backup_runner.py':RUNTIME/'canonical_backup_runner.py',
        BASE/'scripts/install_restore_host.py':RUNTIME/'scripts/install_restore_host.py',
        BASE/'scripts/restore_runtime.py':RUNTIME/'scripts/restore_runtime.py',
        BASE/'scripts/bootstrap_restore_v0_1.sh':RUNTIME/'scripts/bootstrap_restore_v0_1.sh'}
    for target,source in replacements.items():
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_symlink():target.unlink()
        shutil.copyfile(source,target);target.chmod(0o755 if target.suffix in ('.sh','.py') else 0o644)
    (BASE/'infra/docker-compose.override.yml').unlink(missing_ok=True)
    marker=dict(release=NAME,runtime=str(RUNTIME),private=str(PRIVATE),image_archive_sha256=m['offline_image_archive_sha256'])
    write_json(BASE/'infra/access-release.json',marker,0o644)
    manifest=BASE/'secrets/manifest.txt';text=manifest.read_text()
    for secret in (PRIVATE/'compose-env',PRIVATE/'mqtt',PRIVATE/'network-policy.json'):
        if str(secret) not in text:text=text.rstrip()+'\n'+str(secret)+'\n'
    manifest.write_text(text)
    # The full-restore launcher reads this canonical encrypted bundle. Install
    # only after the real network policy is recorded, so fresh restore can gate it.
    bundle=BASE/'secrets/homecontrol-secrets-latest.tar.gz.age'
    checksum=bundle.with_name(bundle.name+'.sha256')
    for path in (bundle,checksum):
        if path.is_symlink():path.unlink()
    shutil.copyfile(Path(kit)/'private/homecontrol-secrets-access.tar.gz.age',bundle);bundle.chmod(0o600)
    checksum.write_text(digest(bundle)+'  '+bundle.name+'\n');checksum.chmod(0o644)
    install_units()


def install_units():
    for relative,text in units(RUNTIME).items():
        path=Path('/etc/systemd/system')/relative;no_symlinks(path);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text);path.chmod(0o644)
    call(['systemctl','daemon-reload'])


def compose(file):
    return ['docker','compose','-p','homecontrol','--profile','ha-growatt','-f',str(file)]


def check_network(expected):
    row=json.loads(call(['docker','network','inspect',expected['name']]).stdout)[0]
    if row['EnableIPv6'] or row['IPAM']['Config'][0]['Subnet']!=expected['subnet']:raise ValueError('Docker network differs from reviewed IPv4 network')
    endpoints={r['Name']:r['IPv4Address'].split('/')[0] for r in row['Containers'].values()}
    if not expected.get('fixed_endpoints') or endpoints!=expected['fixed_endpoints']:
        raise ValueError('Docker endpoint addresses changed; refresh the prepared network inventory')
    call(['nft','list','tables'])
    for family in ('bridge','inet'):
        if call(['nft','list','table',family,'hc41_r10'],allowed=(0,1)).returncode==0:
            raise ValueError('Existing access firewall ownership must be reconciled first')


def wait_backend(timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:5000/health',timeout=3) as response:value=json.load(response)
            if response.status==200 and value.get('db_ok') is True and value.get('mqtt_ok') is True:
                inspected=json.loads(call(['docker','inspect','homecontrol-backend']).stdout)[0]
                sys.path.insert(0,str(RUNTIME/'scripts/hostops'))
                from installation_plan import validate_backend
                if validate_backend(inspected):raise RuntimeError('New backend permissions differ from plan')
                call(['docker','exec','homecontrol-backend','python','-c',
                    'from host_operations_client import HostOperationsClient;c=HostOperationsClient();assert c.call("containers",timeout=5)'])
                return
        except (OSError,ValueError,RuntimeError):time.sleep(.5)
    raise RuntimeError('New backend DB/MQTT/hostops readiness did not pass')


def approval(path):
    value=json.loads(Path(path).read_text())
    import ipaddress
    address=ipaddress.IPv4Address(value['esp_ip'])
    if address.is_loopback or address.is_unspecified or address.is_multicast:raise ValueError('Invalid confirmed ESP IP')
    if value.get('esp_identity_confirmed') is not True or value.get('fixed_ip_confirmed') is not True:
        raise ValueError('ESP identity and stable address must be explicitly confirmed')
    return value


def deploy(kit,approval_file):
    m=verify(kit);confirmed=approval(approval_file);check_network(m['network'])
    previous=json.loads((Path(kit)/'private/rollback.compose.json').read_text())
    for service in SERVICES:
        row=json.loads(call(['docker','inspect','--type','container',
            'zigbee2mqtt' if service=='zigbee2mqtt' else 'homecontrol-'+('ingest' if service=='hc_ingest' else service.removeprefix('homecontrol-'))]).stdout)[0]
        expected=previous['services'][service]
        if row['Image']!=expected['image'] or dict(item.split('=',1) for item in row['Config']['Env'])!=expected['environment']:
            raise ValueError('Running service changed after preparation; refresh the release first')
    if Path('/etc/systemd/system/homecontrol-hostops.service').exists():raise ValueError('Existing hostops installation must be reviewed first')
    state_dir=Path(kit)/'private/transition'
    target_files=[BASE/'infra/docker-compose.yml',BASE/'infra/docker-compose.override.yml',BASE/'scripts/backup_runner.py',
        BASE/'scripts/install_restore_host.py',BASE/'scripts/restore_runtime.py',BASE/'scripts/bootstrap_restore_v0_1.sh',BASE/'secrets/manifest.txt',BASE/'infra/access-release.json',
        BASE/'secrets/homecontrol-secrets-latest.tar.gz.age',BASE/'secrets/homecontrol-secrets-latest.tar.gz.age.sha256']
    guard_files=('homecontrol-mqtt-access.service','docker.service.d/hc-access.conf')
    for name in guard_files:
        if (Path('/etc/systemd/system')/name).exists():raise ValueError('Existing network guard requires ownership review')
    target_files += [Path('/etc/systemd/system')/name for name in units(Path(kit)/'source') if name not in guard_files]
    snapshot(target_files,state_dir)
    enabled={n:call(['systemctl','is-active',n],allowed=(0,3,4)).stdout.strip()=='active' for n in QUIESCE}
    metadata_paths=[BASE/'backups/ai-backup.lock',BASE/'backups/homecontrol-backup.lock',BASE/'infra/private']
    for folder in (BASE/'infra/private',BASE/'backups/ai-control'):
        if folder.exists():metadata_paths.extend([folder,*folder.iterdir()])
    metadata={str(p):dict(uid=p.stat().st_uid,gid=p.stat().st_gid,mode=p.stat().st_mode&0o777,inode=p.stat().st_ino)
        for p in metadata_paths if p.exists()}
    write_json(state_dir/'transition.json',dict(state='preparing',enabled=enabled,metadata=metadata,approval=confirmed))
    try:
        for name in QUIESCE:call(['systemctl','stop',name],allowed=(0,5))
        for service in ('homecontrol-backup.service','homecontrol-ai-weekly-backup.service','homecontrol-full-ai-backup-request.service','homecontrol-restic-check.service','homecontrol-log-maintenance.service','homecontrol-backup-apply.service'):
            if call(['systemctl','is-active','--quiet',service],allowed=(0,3,4)).returncode==0:raise RuntimeError('A backup/unit operation is running')
        call(['docker','stop','--time','30','homecontrol-backend'])
        with ExitStack() as stack:
            locked(stack)
            if all(n in m.get('scope',[]) for n in ('HC-35','HC-36')):
                from climate_handover import reconcile
                reconcile(state_dir,'deploy')
            install_files(kit,confirmed)
        call(['systemctl','enable','--now','homecontrol-mqtt-access.service','homecontrol-hostops.service'])
        call(compose(BASE/'infra/docker-compose.yml')+['up','-d','--no-deps','--no-build','--pull','never',*SERVICES])
        wait_backend()
        for name,wanted in enabled.items():
            if wanted:call(['systemctl','start',name])
        write_json(PRIVATE/'installed.json',dict(release=NAME,state='running_requires_supervised_acceptance',transition=str(state_dir)))
    except Exception:
        try:
            if (BASE/'infra/access-release.json').exists():rollback(kit)
            else:
                restore_snapshot(state_dir)
                for path,meta in metadata.items():os.chown(path,meta['uid'],meta['gid']);os.chmod(path,meta['mode'])
                call(['systemctl','daemon-reload'])
                call(compose(Path(kit)/'private/rollback.compose.json')+['up','-d','--no-deps','--no-build','--pull','never',*SERVICES])
                for name,wanted in enabled.items():
                    if wanted:call(['systemctl','start',name])
            write_json(state_dir/'failure.json',dict(state='failed',rollback_completed=True))
        except Exception:
            write_json(state_dir/'failure.json',dict(state='failed',rollback_completed=False,reconciliation_required=True))
        raise


def rollback(kit):
    kit=Path(kit);state=kit/'private/transition';before=json.loads((state/'transition.json').read_text())
    for name in QUIESCE:call(['systemctl','stop',name],allowed=(0,5))
    for service in ('homecontrol-backup.service','homecontrol-ai-weekly-backup.service','homecontrol-full-ai-backup-request.service','homecontrol-restic-check.service','homecontrol-log-maintenance.service'):
        if call(['systemctl','is-active','--quiet',service],allowed=(0,3,4)).returncode==0:raise RuntimeError('Reconcile running backup before rollback')
    for path in Path('/var/lib/homecontrol-hostops/jobs').glob('*.json'):
        if json.loads(path.read_text()).get('state') in ('queued','running'):
            raise RuntimeError('Reconcile the running host operation before rollback')
    scope=json.loads((kit/'release.json').read_text()).get('scope',[])
    if all(n in scope for n in ('HC-35','HC-36')):
        call(['docker','stop','--time','30','homecontrol-backend'],allowed=(0,1))
        # A failed cutover may have left PostgreSQL stopped. Bring up only this
        # dependency before cancelling intents; the previous backend stays stopped.
        call(compose(kit/'private/rollback.compose.json')+['up','-d','--no-deps','--no-build','--pull','never','postgres'])
        deadline=time.monotonic()+60
        while call(['docker','exec','homecontrol-postgres','sh','-c',
                    'exec pg_isready -U "$POSTGRES_USER" -d "${POSTGRES_DB:-homecontrol}"'],allowed=(0,1,2,3)).returncode:
            if time.monotonic()>=deadline:raise RuntimeError('Rollback database is not ready; keep backend stopped')
            time.sleep(.5)
        from climate_handover import reconcile
        reconcile(state,'rollback')
    call(compose(BASE/'infra/docker-compose.yml')+['stop',*SERVICES])
    call(['systemctl','stop','homecontrol-hostops.service'],allowed=(0,5))
    call(['systemctl','disable','homecontrol-hostops.service'],allowed=(0,1,5))
    with ExitStack() as stack:
        locked(stack)
        if (BASE/'backups/ai-control/ai-power-state.json').exists():
            transfer_state(BASE/'backups/ai-control/ai-power-state.json',BASE/'backups/ai-power-state.json','access rollback')
        policy=json.loads((PRIVATE/'network-policy.json').read_text());policy.update(mode='rollback',owned_chain=True)
        firewall(policy);write_json(PRIVATE/'network-policy.json',policy)
        restore_snapshot(state)
        for name,meta in before['metadata'].items():
            path=Path(name)
            if path.name.endswith('.lock') and path.stat().st_ino!=meta['inode']:raise RuntimeError('Refusing rollback onto a different lock inode')
            os.chown(path,meta['uid'],meta['gid']);path.chmod(meta['mode'])
    call(['systemctl','daemon-reload'])
    call(compose(kit/'private/rollback.compose.json')+['up','-d','--no-deps','--no-build','--pull','never',*SERVICES])
    for name,wanted in before['enabled'].items():
        if wanted:call(['systemctl','start',name])
    write_json(state/'rollback.json',dict(completed=True,network_restriction_retained=True))


def restore_jobs(recovered, target):
    """A repeated restore may retain identical receipts, never replace newer jobs."""
    recovered=Path(recovered);target=Path(target)
    if not recovered.exists():return
    no_symlinks(recovered);no_symlinks(target)
    incoming={p.name:p.read_bytes() for p in recovered.iterdir() if p.is_file() and not p.is_symlink()}
    if len(incoming)!=len(list(recovered.iterdir())):raise ValueError('Unexpected recovered journal entry')
    if target.exists():
        current={p.name:p.read_bytes() for p in target.iterdir() if p.is_file() and not p.is_symlink()}
        if len(current)!=len(list(target.iterdir())) or current and current!=incoming:
            raise ValueError('Existing host job journal must be reconciled before restore')
        if current==incoming:return
    target.mkdir(parents=True,exist_ok=True);target.chmod(0o700)
    for name,data in incoming.items():
        path=target/name;path.write_bytes(data);path.chmod(0o600)


def restore_prepare():
    marker=json.loads((BASE/'infra/access-release.json').read_text())
    images=RUNTIME/'images'
    info=json.loads((images/'manifest.json').read_text());archive=images/info['archive']
    if digest(archive)!=marker['image_archive_sha256'] or digest(archive)!=info['sha256']:raise ValueError('Restore requires the verified offline deployment images')
    if call(['docker','image','inspect',*info['images']],allowed=(0,1)).returncode!=0:
        call(['docker','load','-i',str(archive)])
    if not (PRIVATE/'images').exists():shutil.copytree(images,PRIVATE/'images')
    model=json.loads((RUNTIME/'runtime.compose.json').read_text());net=model['networks']['default']['name']
    policy=json.loads((PRIVATE/'network-policy.json').read_text())
    if not policy.get('esp_confirmed'):raise ValueError('Restored ESP address requires confirmation')
    if call(['docker','network','inspect',net],allowed=(0,1)).returncode!=0:
        import ipaddress
        gateway=str(next(ipaddress.ip_network(policy['docker_subnet']).hosts()))
        call(['docker','network','create','--subnet',policy['docker_subnet'],'--gateway',gateway,net])
    for name in ('ai-backup.lock','homecontrol-backup.lock'):
        path=BASE/'backups'/name;no_symlinks(path);path.parent.mkdir(exist_ok=True);path.touch(exist_ok=True)
    recovered=PRIVATE/'host-jobs'
    restore_jobs(recovered,Path('/var/lib/homecontrol-hostops/jobs'))
    permissions();install_units()


def start_runtime():
    if (RUNTIME/'binding-release.json').is_file():
        from climate_handover import reconcile
        reconcile(PRIVATE/'restore-handover'/uuid.uuid4().hex,'restore')
    call(['systemctl','enable','--now','homecontrol-mqtt-access.service','homecontrol-hostops.service'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('check','deploy','rollback','restore-prepare','start-runtime'))
    parser.add_argument('--kit',type=Path,default=BASE/'backups/releases'/NAME);parser.add_argument('--approval',type=Path)
    args=parser.parse_args()
    try:
        if args.action=='check':verify(args.kit)
        else:
            if os.geteuid()!=0:raise PermissionError('Explicit root operation required')
            if args.action=='deploy':
                if not args.approval:raise ValueError('Confirmed ESP approval file required')
                deploy(args.kit,args.approval)
            elif args.action=='rollback':rollback(args.kit)
            elif args.action=='restore-prepare':restore_prepare()
            else:start_runtime()
        print(json.dumps(dict(action=args.action,success=True)))
    except Exception as exc:raise SystemExit('Access operation stopped ('+type(exc).__name__+'); reconcile the private transition record')
