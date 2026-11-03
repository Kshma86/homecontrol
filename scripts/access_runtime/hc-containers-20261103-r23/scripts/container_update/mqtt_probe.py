#!/usr/bin/env python3
"""MQTT auth/ACL/retained persistence transition on synthetic offline data."""
import hashlib
import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import uuid

ROOT=Path('/srv/docker/homecontrol/maintenance/container-update-20261103')


def call(args,**kwargs):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=45,**kwargs)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args()
    if args.attempt<1:raise ValueError('Positive attempt required')
    suffix='' if args.attempt==1 else '-'+str(args.attempt)
    fixture=ROOT/('mqtt-synthetic'+suffix);fixture.mkdir(mode=0o755,exist_ok=False)
    (fixture/'data').mkdir(mode=0o755)
    old=json.loads((ROOT/'baseline.json').read_text())['containers']['homecontrol-mqtt']['image']
    new=next(r['image'] for r in json.loads((ROOT/'upstream/pulled-images.json').read_text()) if r['name']=='mqtt')
    password=secrets.token_urlsafe(24)
    mount='type=bind,src='+str(fixture)+',dst=/fixture'
    for number,user in enumerate(('backend','observer')):
        command=['docker','run','--rm','--network','none','--read-only','--user','1000:1000',
                 '--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,size=16m','--mount',mount,
                 '--entrypoint','mosquitto_passwd',old,'-b',*(['-c'] if number==0 else []),'/fixture/passwd',user,password]
        call(command)
    (fixture/'passwd').chmod(0o644)
    (fixture/'acl').write_text('topic readwrite fixture/legacy\nuser backend\ntopic readwrite #\nuser observer\ntopic read #\n')
    (fixture/'mosquitto.conf').write_text('per_listener_settings true\npersistence true\npersistence_location /fixture/data/\n'
        'autosave_interval 1\nlog_dest stdout\nlog_type all\nmax_packet_size 268435455\nlistener 1883 127.0.0.1\nallow_anonymous true\n'
        'acl_file /fixture/acl\nlistener 1884 127.0.0.1\nallow_anonymous false\npassword_file /fixture/passwd\nacl_file /fixture/acl\n')
    report={'ok':False,'production_mounts':False,'network':'none','synthetic_credentials':True,'stages':[]}
    name=None
    def start(image,stage):
        nonlocal name
        name='hc-mqtt-update-probe-'+stage+'-'+uuid.uuid4().hex[:8]
        call(['docker','run','-d','--rm','--name',name,'--label','hc.container-update=20261103',
              '--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges',
              '--memory','256m','--cpus','1','--pids-limit','64','--mount',mount,
              '--entrypoint','mosquitto',image,'-c','/fixture/mosquitto.conf'])
        for _ in range(30):
            status=json.loads(call(['docker','inspect',name]).stdout)[0]['State']
            if not status['Running']:raise ValueError('Probe broker exited')
            r=subprocess.run(['docker','exec',name,'mosquitto_pub','-h','127.0.0.1','-p','1884','-u','backend','-P',password,
                              '-t','fixture/ready','-m','ready'],capture_output=True,timeout=5)
            if r.returncode==0:return
            time.sleep(.2)
        raise TimeoutError('Probe broker not ready')
    def stop(stage):
        nonlocal name
        log=call(['docker','logs',name]);(fixture/(stage+'.log')).write_text(log.stdout+log.stderr)
        call(['docker','stop','--time','15',name]);name=None
    def pub(topic,payload,*,user='backend',retained=True):
        auth=[] if user is None else ['-u',user,'-P',password]
        return subprocess.run(['docker','exec',name,'mosquitto_pub','-h','127.0.0.1','-p','1883' if user is None else '1884',
            '-V','5','-q','1',*auth,'-t',topic,'-m',payload,*(['-r'] if retained else [])],capture_output=True,text=True,timeout=10)
    def retained(topic,expected):
        out=call(['docker','exec',name,'mosquitto_sub','-h','127.0.0.1','-p','1884','-V','5',
                  '-u','observer','-P',password,'-t',topic,'-C','1','-W','5']).stdout.strip()
        if out!=expected:raise ValueError('Retained value differs')
    try:
        start(old,'old');assert pub('fixture/persistence','before').returncode==0
        assert pub('fixture/legacy','legacy',user=None).returncode==0
        retained('fixture/persistence','before');stop('old')
        shutil.copyfile(fixture/'data/mosquitto.db',fixture/'old-mosquitto.db')
        start(new,'new');retained('fixture/persistence','before');retained('fixture/legacy','legacy')
        denied=pub('fixture/persistence','forbidden',user='observer')
        retained('fixture/persistence','before')
        logs=call(['docker','logs',name])
        if denied.returncode==0 and 'Denied PUBLISH' not in logs.stdout+logs.stderr:
            raise ValueError('Missing explicit broker evidence of read-only publish denial')
        wrong=subprocess.run(['docker','exec',name,'mosquitto_pub','-h','127.0.0.1','-p','1884','-V','5',
            '-u','backend','-P','wrong-synthetic-password','-t','fixture/persistence','-m','forbidden'],capture_output=True,timeout=10)
        if wrong.returncode==0:raise ValueError('Incorrect password accepted')
        assert pub('fixture/persistence','after').returncode==0
        retained('fixture/persistence','after');stop('new')
        report['stages']=['old_write','new_read_old_persistence','new_auth_acl_enforced','new_write']
        # Rollback always restores the pre-stop DB copy, regardless of format.
        shutil.copyfile(fixture/'old-mosquitto.db',fixture/'data/mosquitto.db')
        start(old,'rollback');retained('fixture/persistence','before');stop('rollback')
        report.update(ok=True,rollback_old_persistence_verified=True,anonymous_legacy_preserved=True,
                      authenticated_access_verified=True,observer_publish_denied=True,wrong_password_denied=True)
    finally:
        if name:
            logs=subprocess.run(['docker','logs',name],capture_output=True,text=True)
            (fixture/'failure-broker.log').write_text(logs.stdout+logs.stderr)
            subprocess.run(['docker','rm','-f',name],capture_output=True)
        (ROOT/('mqtt-synthetic-result'+suffix+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
