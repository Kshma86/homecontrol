#!/usr/bin/env python3
"""One supervised r22 -> r23 container update, including mutable-data rollback."""
from contextlib import ExitStack
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid

sys.dont_write_bytecode=True
BASE=Path('/srv/docker/homecontrol')
NAME='hc-containers-20261103-r23'
OLD='hc-audit-20261103-r22'
KIT=BASE/'backups/releases'/NAME
PRIVATE=KIT/'private'
SOURCE=KIT/'source'
HOST_EXECUTOR=SOURCE/'scripts/container_update/backup_helper.py'
HOST_EXECUTOR_SHA='09b8cd6c55432c7f5363d15ed0084ab6ecd9c792b2adab0c8dde5c36eb0ec0af'
START_GROUPS=(('mqtt',),('zigbee2mqtt',),('ai-server','mdns','hc_ingest',
    'homecontrol-tuya-poller','homecontrol-gree-climate','homecontrol-xiaomi-x10',
    'homecontrol-ha-growatt-poller'),('backend','frontend','proxy'))
STOP_PEERS=('proxy','frontend','mdns','ai-server','hc_ingest','homecontrol-tuya-poller',
    'homecontrol-gree-climate','homecontrol-xiaomi-x10','homecontrol-ha-growatt-poller','zigbee2mqtt','mqtt')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def say(message):print(message,flush=True)


def firewall(e,private):
    policy=Path(private)/'network-policy.json';data=read(policy)
    if data.get('mode')!='authenticated' or data.get('owned_chain') is not True:raise ValueError('MQTT access policy changed')
    result={'policy_sha256':sha(policy)}
    for family in ('bridge','inet'):
        rows=json.loads(e.call(['nft','-j','list','table',family,'hc41_r10']))['nftables']
        result[family]=sorted(json.dumps(e.normalize_nft(row),sort_keys=True) for row in rows if 'metainfo' not in row)
        if not any('rule' in row for row in rows):raise ValueError('Missing MQTT access rules')
    return result


def bridge(e,expected_version):
    def topic(name):
        raw=e.call(['docker','exec','homecontrol-backend','python','/app/mqtt_read_probe.py','--topic',name],timeout=30)
        return json.loads(raw)
    info=topic('zigbee/bridge/info');devices=topic('zigbee/bridge/devices')
    if info.get('version')!=expected_version:raise ValueError('Zigbee bridge version differs')
    if not isinstance(devices,list):raise ValueError('Invalid Zigbee device inventory')
    identities=sorted(d['ieee_address'] for d in devices)
    if len(identities)!=len(set(identities)) or len(identities)<2:raise ValueError('Incomplete Zigbee identities')
    return {'version':info['version'],'identities':identities,'coordinator':info.get('coordinator')}


def settle(core,*,release_units):
    sys.path.insert(0,str(SOURCE/'scripts/audit_release'))
    from schedules import schedule_plan,check_schedules
    adapter=load('r23_timer_settle',SOURCE/'scripts/audit_release/timer_settle.py')
    return adapter.check(core,check_schedules,schedule_plan(core),release_units=release_units)


def platform_probes(core,manifest,previous=False):
    module=load('r23_readonly_platform',SOURCE/'scripts/security_release/activate.py')
    return {'ha':module.ha_ready(core,manifest,previous=previous),'postgres':module.postgres_ready(core)}


def private_mqtt_probe(core,e,stage,source):
    """Clone real broker config and persistence; connect only inside an island."""
    destination=stage/'mqtt/broker'
    if destination.is_symlink() or not destination.is_relative_to(PRIVATE):raise ValueError('Unsafe private broker stage')
    if destination.exists():shutil.rmtree(destination)
    for path in (source,*source.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):raise ValueError('Invalid live broker config entry')
    shutil.copytree(source,destination)
    config=destination/'mosquitto.conf';text=config.read_text()
    # Preserve the 2.0 default MQTT packet limit across the 2.1 default change.
    if not re.search(r'^\s*max_packet_size\s+',text,re.M):
        config.write_text(text.rstrip()+'\nmax_packet_size 268435455\n')
    for path in (destination,*destination.rglob('*')):
        os.chown(path,1883,1883);path.chmod(0o700 if path.is_dir() else 0o600)
    work=PRIVATE/'real-mqtt-probe';work.mkdir(mode=0o700)
    for part in ('data','log'):
        path=work/part;path.mkdir(mode=0o700);os.chown(path,1883,1883)
    db=BASE/'infra/mqtt/data/mosquitto.db'
    if db.is_file():
        shutil.copyfile(db,work/'data/mosquitto.db');os.chown(work/'data/mosquitto.db',1883,1883)
    image=core.load()['images']['mqtt'];name='hc-r23-real-mqtt-'+uuid.uuid4().hex[:10]
    base=['docker','run','--network','none','--read-only','--user','0:0','--cap-drop','ALL',
          '--cap-add','SETUID','--cap-add','SETGID','--security-opt','no-new-privileges',
          '--memory','256m','--cpus','1','--pids-limit','64',
          '--mount','type=bind,src='+str(destination)+',dst=/mosquitto/config,readonly',
          '--mount','type=bind,src='+str(work/'data')+',dst=/mosquitto/data',
          '--mount','type=bind,src='+str(work/'log')+',dst=/mosquitto/log']
    e.call([*base,'--rm','--entrypoint','mosquitto',image,'-c','/mosquitto/config/mosquitto.conf','--test-config'])
    e.call([*base,'-d','--rm','--name',name,'--label','hc.container-update=20261103','--entrypoint','mosquitto',image,'-c','/mosquitto/config/mosquitto.conf'])
    try:
        client=core.load()['baseline']['homecontrol-backend']['image']
        code='''import os,time,paho.mqtt.client as mqtt
from mqtt_credentials import configure_mqtt_auth
result=[]
c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
configure_mqtt_auth(c)
c.on_connect=lambda client,userdata,flags,rc:result.append(rc)
c.connect('127.0.0.1',int(os.getenv('MQTT_PORT','1883')),keepalive=10)
end=time.monotonic()+8
while not result and time.monotonic()<end:c.loop(timeout=.1)
c.disconnect()
assert result==[0], 'MQTT authentication failed'
print('backend_authentication_verified_without_publish_or_subscription')
'''
        # Docker reads only the new private copies after real local sudo.
        command=['docker','run','--rm','--network','container:'+name,'--read-only','--user','0:0','--cap-drop','ALL',
                 '--security-opt','no-new-privileges','--env-file',str(stage/'compose-env/backend.env'),
                 '--mount','type=bind,src='+str(stage/'mqtt/credentials/backend.password')+',dst=/run/secrets/hc-mqtt.password,readonly',
                 '--entrypoint','python',client,'-B','-c',code]
        end=time.monotonic()+30
        while True:
            try:e.call(command,timeout=15);break
            except RuntimeError:
                if time.monotonic()>end:raise
                time.sleep(.5)
    finally:
        e.call(['docker','logs',name]);e.call(['docker','stop','--time','20',name])
    e.write(PRIVATE/'real-mqtt-proof.json',{'ok':True,'production_config_mounted':False,
            'private_config_copy_validated':True,'private_persistence_copy_loaded':db.is_file(),
            'backend_auth_verified':True,'client_publish_commands':0,'network':'isolated container namespace'})


class Cutover:
    def __init__(self,core,e,manifest,saved,before_firewall,before_bridge,data):
        self.core,self.e,self.m,self.saved=core,e,manifest,saved
        self.before_firewall,self.before_bridge,self.data=before_firewall,before_bridge,data
        self.install_started=False
        self.app_stop_attempted=False
        self.hostops_stop_attempted=False
        self.rollback_attempted=False

    def quiesce(self):
        self.core.guard_runtime(self.m);self.e.idle();self.e.physical_guard(self.core)

    def stop(self):
        c=self.core;e=self.e
        c.phase('stop_container_update_services');self.hostops_stop_attempted=True
        e.call(['systemctl','stop','homecontrol-hostops.service'],timeout=240)
        e.idle();e.physical_guard(c)
        self.app_stop_attempted=True
        e.call(['docker','stop','--time','60','homecontrol-backend'],timeout=100)
        c.reconcile('deploy')
        for service in STOP_PEERS:
            e.call(['docker','stop','--time','60',c.container(service)],timeout=100)
        proof=self.data.capture(c.STATE/'application-data');e.write(c.STATE/'application-data-proof.json',proof)

    def install(self):
        self.core.phase('install_container_update_runtime');self.install_started=True
        self.core.install_files(self.m)

    def start(self):
        c=self.core;e=self.e
        c.phase('start_container_update_services')
        e.call(['systemctl','restart','homecontrol-mqtt-access.service'])
        if firewall(e,c.PRIVATE)!=self.before_firewall:raise ValueError('MQTT access rules changed')
        e.call(['systemctl','start','homecontrol-hostops.service'])
        for group in START_GROUPS:
            e.call([*c.compose(BASE/'infra/docker-compose.yml'),'up','-d','--no-deps','--no-build','--pull','never',*group],timeout=240)

    def verify(self):
        c=self.core;e=self.e;c.phase('container_update_readiness')
        c.wait_ready(self.m);platform_probes(c,self.m)
        e.device_connections();after=bridge(e,'2.14.3')
        if after['identities']!=self.before_bridge['identities']:raise ValueError('Zigbee device identities changed')
        e.write(PRIVATE/'zigbee-live-proof-private.json',after)
        e.write(c.PRIVATE/'installed.json',{'release':NAME,'state':'running_requires_backup_restore','transition':str(c.STATE)})

    def resume(self):
        # Keep schedules paused until the fresh post-update backup/restore passes.
        pass

    def rollback(self):
        c=self.core;e=self.e;self.rollback_attempted=True;c.phase('container_update_rollback')
        if not self.app_stop_attempted:
            if self.hostops_stop_attempted:e.call(['systemctl','start','homecontrol-hostops.service'])
            e.resume(self.saved)
            e.write(c.STATE/'result.json',{'state':'cancelled_before_app_stop','ok':False,'active_release':OLD})
            return
        if read(BASE/'infra/access-release.json').get('release') not in (NAME,OLD):raise ValueError('Later release blocks rollback')
        for unit in self.saved:e.call(['systemctl','stop',unit])
        e.call(['systemctl','stop','homecontrol-hostops.service'],timeout=240)
        for service in self.m['changed_services']:
            name=c.container(service)
            row=subprocess.run(['docker','inspect','--type','container',name],capture_output=True,text=True,timeout=15)
            if row.returncode:
                if 'no such' not in row.stderr.lower():raise RuntimeError('Cannot inspect rollback service')
                continue
            e.call(['docker','stop','--time','60',name],timeout=100)
        c.reconcile('rollback')
        c.platform().restore_snapshot(c.STATE)
        if (c.STATE/'application-data/metadata.json').exists():self.data.restore(c.STATE/'application-data')
        e.call(['systemctl','daemon-reload'])
        e.call(['systemctl','restart','homecontrol-mqtt-access.service'])
        e.call(['systemctl','start','homecontrol-hostops.service'])
        for group in START_GROUPS:
            e.call([*c.compose(BASE/'infra/docker-compose.yml'),'up','-d','--no-deps','--no-build','--pull','never',*group],timeout=240)
        c.wait_ready(self.m,previous=True);e.device_connections()
        old_bridge=bridge(e,'2.8.0')
        if old_bridge['identities']!=self.before_bridge['identities']:raise ValueError('Rollback Zigbee identities differ')
        if firewall(e,c.OLD_PRIVATE)!=self.before_firewall:raise ValueError('Rollback MQTT access differs')
        e.resume(self.saved);settle(c,release_units=False)
        e.write(c.STATE/'result.json',{'state':'rolled_back','ok':True,'active_release':OLD,
            'pre_update_backup_restore_preserved':True,'post_failure_remote_backup_not_repeated':True})


def rollback_once(context):
    if context.rollback_attempted:return
    if not context.app_stop_attempted:context.rollback();return
    with ExitStack() as stack:context.e.common_locks(stack);context.rollback()


def interrupted(signum,frame):
    raise InterruptedError('Supervised container update interrupted')


def execute(core,e):
    manifest=core.verify()
    if read(BASE/'infra/access-release.json').get('release')!=OLD:raise ValueError('Expected r22 baseline')
    e.call(['/usr/bin/python3',BASE/'maintenance/host-update-20261103/source/check.py','postcheck'],timeout=600)
    core.guard_runtime(manifest);e.idle();e.space_guard()
    reserve=8*1024**3+2*(PRIVATE/'access-images.tar.gz').stat().st_size
    storage=os.statvfs(BASE/'infra/ssh')
    if storage.f_bavail*storage.f_frsize<reserve:raise ValueError('Insufficient runtime cache reserve')
    before_firewall=firewall(e,core.OLD_PRIVATE);before_bridge=bridge(e,'2.8.0')
    e.write(PRIVATE/'before-firewall.json',before_firewall)
    e.write(PRIVATE/'before-bridge-private.json',before_bridge)
    platform_probes(core,manifest,previous=True)
    with ExitStack() as stack:e.common_locks(stack)
    saved={};context=None;completed=False
    try:
        saved=e.pause()
        core.phase('full_existing_repository_check');say('Teljes repository-ellenőrzés indul, az éles szolgáltatások futnak.')
        sys.path.insert(0,str(SOURCE/'infra/backend'))
        from router_backup import RouterRepository
        settings=read(BASE/'backups/backup_settings.json');core.ROUTER_SETTINGS=settings
        repo=RouterRepository(settings,cache=PRIVATE/'repository-check-cache');repo.prepare();repo.check()
        e.backup_restore('pre',{'containers':manifest['baseline']})
        model=read(BASE/'infra/docker-compose.yml')
        sources=[Path(v['source']) for v in model['services']['mqtt']['volumes'] if v.get('target')=='/mosquitto/config']
        if len(sources)!=1 or not sources[0].is_relative_to(BASE/'infra/ssh'):raise ValueError('Unexpected broker config source')
        original=core.encrypted_bundle
        def bundle(stage):private_mqtt_probe(core,e,stage,sources[0]);return original(stage)
        core.encrypted_bundle=bundle
        core.phase('prepare_new_private_runtime');core.prepare_private(manifest)
        core.guard_runtime(manifest);e.idle();e.physical_guard(core)
        targets=list(dict.fromkeys([*core.target_files(),BASE/'infra/docker-compose.override.yml']))
        core.platform().snapshot(targets,core.STATE)
        e.write(core.STATE/'transition.json',{'release':NAME,'active_timers':saved,'state':'starting'})
        data=load('r23_mutable_data',SOURCE/'scripts/container_update/data_snapshot.py')
        context=Cutover(core,e,manifest,saved,before_firewall,before_bridge,data)
        with ExitStack() as stack:
            e.common_locks(stack);core.switch(context)
        core.phase('post_update_backup_restore');e.RUNTIME=core.RUNTIME
        proof=e.backup_restore('post',{'containers':manifest['baseline']})
        e.resume(saved)
        schedules=settle(core,release_units=True)
        capture=load('r23_live_capture',SOURCE/'scripts/audit_release/postcheck.py').capture
        live=capture(core,manifest,final=False)
        for name,row in live['containers'].items():
            if row['running']!=manifest['baseline'][name]['running']:raise ValueError('Unexpected component running state')
        if firewall(e,core.PRIVATE)!=before_firewall:raise ValueError('Final MQTT access changed')
        live.update(active_timers=schedules['timers'],scheduled_units=schedules,backup=proof,
                    audit_checked=46,audit_in_progress=['HC-41','HC-43'])
        core.platform().write_json(KIT/'evidence/post-live-check.json',live,0o644)
        core.platform().write_json(KIT/'evidence/router-live-acceptance.json',dict(proof,release=NAME),0o644)
        result={'ok':True,'release':NAME,'state':'container_updates_backup_restore_verified',
                'changed_images':len(manifest['changed_services']),'recreated_services':len(manifest['changed_services']),
                'ai_enabled':False,'hc43':'in_progress',**proof}
        core.platform().write_json(KIT/'deployment-status.json',result,0o644)
        e.write(core.PRIVATE/'installed.json',{'release':NAME,'state':result['state'],'transition':str(core.STATE)})
        e.write(core.STATE/'result.json',result);completed=True;say(json.dumps(result))
    except BaseException:
        if context is not None:rollback_once(context)
        raise
    finally:
        if not completed and context is None and saved:e.resume(saved)


def main():
    os.umask(0o077)
    if os.geteuid()!=0:raise PermissionError('Local sudo is required; Docker is not a host-root fallback')
    if sys.argv[1:]==['status']:
        output={'release':NAME,'started':(PRIVATE/'activation-attempt.json').exists()}
        for key,path in (('deployment',KIT/'deployment-status.json'),('progress',PRIVATE/'progress.json'),
                         ('error',PRIVATE/'activation-error.json'),('transition',PRIVATE/'transition/result.json')):
            if path.is_file() and not path.is_symlink():output[key]=read(path)
        say(json.dumps(output,indent=2));return
    PRIVATE.mkdir(mode=0o700,exist_ok=True)
    if any(path.is_symlink() for path in (PRIVATE,*PRIVATE.parents)):raise ValueError('Invalid private directory')
    os.chown(PRIVATE,0,0);PRIVATE.chmod(0o700)
    archive=PRIVATE/'access-images.tar.gz'
    if archive.is_symlink() or not archive.is_file():raise ValueError('Regular offline image archive required')
    os.chown(archive,0,0);archive.chmod(0o600)
    if sys.argv[1:]==['_worker']:
        signal.signal(signal.SIGTERM,interrupted)
        signal.signal(signal.SIGINT,interrupted)
        if sha(HOST_EXECUTOR)!=HOST_EXECUTOR_SHA:raise ValueError('Accepted backup helper changed')
        e=load('r23_backup_helper',HOST_EXECUTOR);e.STATE=PRIVATE;e.RUNTIME=BASE/'scripts/access_runtime'/OLD
        e.say=lambda message:say(message.replace('Hostkarbantartás:','Konténerfrissítés:',1))
        e.LOG=(PRIVATE/'activation-private.log').open('x')
        try:
            with (PRIVATE/'operator.lock').open('a') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                core=load('r23_core',SOURCE/'scripts/f10_release/deploy.py')
                core.call=lambda args,**kw:adapter_call(e,args,**kw)
                previous_phase=core.phase
                def phase(name):
                    e.PHASE=name;say('Konténerfrissítés: '+name);previous_phase(name)
                core.phase=phase
                execute(core,e)
        except BaseException as error:
            traceback.print_exc(file=e.LOG);e.LOG.flush()
            e.write(PRIVATE/'activation-error.json',{'error_type':type(error).__name__,'phase':e.PHASE})
            say('Az r23 megállt: '+type(error).__name__+'. Privát napló megőrizve; ne ismételd vakon.');raise SystemExit(1)
        finally:e.LOG.close()
        return
    if len(sys.argv)!=1:raise ValueError('No activation arguments supported')
    with (PRIVATE/'activation-attempt.json').open('x') as stream:json.dump({'release':NAME,'one_shot':True},stream)
    args=['systemd-run','--quiet','--wait','--pipe','--collect','--unit=homecontrol-r23-container-update',
          '--property=Type=exec','--property=KillMode=mixed','--property=RuntimeMaxSec=28800',
          '--property=TimeoutStopSec=900','--property=UMask=0077','/usr/bin/python3',str(Path(__file__).resolve()),'_worker']
    raise SystemExit(subprocess.run(args).returncode)


def adapter_call(e,args,*,allowed=(0,),timeout=180,extra_env=None,**kwargs):
    # Frozen read-only core helpers expect a CompletedProcess and bytes output.
    # Use the accepted private logger; never return raw command output publicly.
    if set(kwargs)-{'text','input'}:raise ValueError('Unexpected core command options')
    env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    env.update(DOCKER_HOST='unix:///var/run/docker.sock',PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',LC_ALL='C')
    env.update(extra_env or {})
    result=subprocess.run(args,capture_output=True,env=env,timeout=timeout,**kwargs)
    if e.LOG:
        decode=lambda value:value.decode(errors='replace') if isinstance(value,bytes) else value
        output='[decrypted binary stdout withheld]\n' if Path(str(args[0])).name=='age' and '-d' in args else decode(result.stdout)
        e.LOG.write('\nCOMMAND '+repr(list(map(str,args)))+'\n'+output+decode(result.stderr));e.LOG.flush()
    if result.returncode not in allowed:raise RuntimeError('Private operation failed: '+str(args[0]))
    return result


if __name__=='__main__':main()
