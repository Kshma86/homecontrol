#!/usr/bin/env python3
"""UID-1883 integration test using disposable Docker data only, no host binds."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import uuid

ROOT=Path('/srv/docker/homecontrol')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,required=True);args=parser.parse_args()
    work=ROOT/'maintenance/container-update-20261103'/('mqtt-owner-island-'+str(args.attempt));work.mkdir(mode=0o700)
    lock=json.loads((ROOT/'maintenance/container-update-20261103/candidate-image-lock-final.json').read_text())
    image=lock['homecontrol-mqtt'];backend=lock['homecontrol-backend']
    volume='hc-r23-owner-'+uuid.uuid4().hex[:12];broker=volume+'-broker';password='hc-synthetic-owner-probe-only'
    def call(name,command,check=True):
        result=subprocess.run(command,capture_output=True,text=True,timeout=45)
        (work/(name+'.log')).write_text(result.stdout+result.stderr)
        if check and result.returncode:raise RuntimeError('Synthetic island stage failed: '+name)
        return result
    call('volume-create',['docker','volume','create','--label','hc.container-update=owner-island',volume]);started=False
    mount='type=volume,src='+volume+',dst=/fixture'
    base=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--tmpfs','/tmp:rw,nosuid,nodev,size=16m','--mount',mount]
    try:
        script='''mkdir -p /fixture/broker /fixture/data /fixture/log /fixture/credentials
cat > /fixture/broker/mosquitto.conf <<'CONF'
per_listener_settings true
persistence true
persistence_location /fixture/data/
log_dest stdout
log_dest file /fixture/log/broker.log
max_packet_size 268435455
listener 1883 127.0.0.1
allow_anonymous true
acl_file /fixture/broker/acl
listener 1884 127.0.0.1
allow_anonymous false
password_file /fixture/broker/passwd
acl_file /fixture/broker/acl
CONF
printf 'topic read fixture/legacy\nuser backend\ntopic readwrite #\n' > /fixture/broker/acl
mosquitto_passwd -b -c /fixture/broker/passwd backend "$SYNTHETIC_PASSWORD"
printf '%s' "$SYNTHETIC_PASSWORD" > /fixture/credentials/hc-mqtt.password
chown -R 1883:1883 /fixture/broker /fixture/data /fixture/log
chmod 700 /fixture/broker /fixture/data /fixture/log /fixture/credentials
chmod 600 /fixture/broker/*
chmod 400 /fixture/credentials/hc-mqtt.password
'''
        call('initialize',[*base,'--user','0:0','--cap-add','CHOWN','--cap-add','FOWNER','--cap-add','DAC_OVERRIDE',
            '--env','SYNTHETIC_PASSWORD='+password,'--entrypoint','sh',image,'-ec',script])
        frozen=call('frozen-config-test',[*base,'--user','0:0','--cap-add','SETUID','--cap-add','SETGID',
            '--entrypoint','mosquitto',image,'-c','/fixture/broker/mosquitto.conf','--test-config'],check=False)
        if frozen.returncode==0 or 'Unable to open config file' not in frozen.stdout+frozen.stderr:
            raise ValueError('Expected frozen permission failure was not reproduced')
        owned=call('owned-config-test',[*base,'--user','1883:1883','--entrypoint','mosquitto',image,
            '-c','/fixture/broker/mosquitto.conf','--test-config'])
        call('start',['docker','run','--rm','-d','--name',broker,'--label','hc.container-update=owner-island',
            '--network','none','--read-only','--user','1883:1883','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--mount',mount,'--memory','256m','--pids-limit','64','--entrypoint','mosquitto',image,'-c','/fixture/broker/mosquitto.conf'])
        started=True
        path=ROOT/'backups/releases/hc-containers-20261103-r23/source/scripts/container_update/activate.py'
        spec=importlib.util.spec_from_file_location('frozen_owner_client_source',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        code=next(v for v in module.private_mqtt_probe.__code__.co_consts if isinstance(v,str) and
            'backend_authentication_verified_without_publish_or_subscription' in v)
        call('backend-auth',['docker','run','--rm','--network','container:'+broker,'--read-only','--user','0:0',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--mount',mount+',readonly',
            '--env','MQTT_HOST=127.0.0.1','--env','MQTT_PORT=1884','--env','MQTT_USERNAME=backend',
            '--env','MQTT_PASSWORD_FILE=/fixture/credentials/hc-mqtt.password','--entrypoint','python',backend,'-B','-c',code])
        call('publish',['docker','exec',broker,'mosquitto_pub','-h','127.0.0.1','-p','1884','-u','backend','-P',password,
            '-t','fixture/retained','-m','synthetic','-r','-q','1'])
        call('broker',['docker','logs',broker]);call('stop',['docker','stop','--time','15',broker]);started=False
        call('files',[*base,'--user','1883:1883','--entrypoint','sh',image,'-ec',
            'test -s /fixture/data/mosquitto.db && test -s /fixture/log/broker.log'])
        result={'ok':True,'mosquitto_image':image,'backend_image':backend,'production_mounts':False,'host_bind_mounts':False,
            'network':'isolated container namespace','synthetic_credentials':True,'config_uid':1883,
            'config_directory_mode':'0700','config_file_mode':'0600','frozen_root_test_exit':frozen.returncode,
            'owner_test_exit':owned.returncode,'broker_uid':1883,'broker_added_capabilities':[],
            'backend_authentication':'verified using exact frozen client code','persistence_saved':True,
            'log_writable':True,'deployment_performed':False}
        (work/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:
        if started:call('failure-stop',['docker','stop','--time','15',broker],check=False)
        call('volume-remove',['docker','volume','rm',volume])


if __name__=='__main__':main()
