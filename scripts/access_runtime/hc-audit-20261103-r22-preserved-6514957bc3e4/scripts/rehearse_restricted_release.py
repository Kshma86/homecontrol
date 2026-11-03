#!/usr/bin/env python3
"""Real isolated release/rollback/release and broker verification; no production access."""
import json
from pathlib import Path
import rehearse_audit_release as lab

lab.RELEASE=lab.BASE/'backups/releases/hc-refactor-ai-offline-20261027-r6'
lab.DB='hc-r5-ai-offline-db'
lab.PREFIX='hc-r5-lab-'
lab.VOLUME_PREFIX='hc-r5-ai-offline-'
lab.EVIDENCE=Path('/tmp/hc-ai-offline-20261027')

BROKER_PROBE=r'''
import json,threading,time
import paho.mqtt.client as mqtt
from mqtt_monitor_service import MqttClientService
received=[];ready=threading.Event()
tracked={'homecontrol/cmd/tuya/Mosógép/switch','homecontrol/cmd/tuya/renamed/switch','homecontrol/cmd/tuya/hc-r5-control/switch'}
observer=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
observer.on_connect=lambda client,*args:client.subscribe('homecontrol/cmd/tuya/#',qos=1)
observer.on_subscribe=lambda *args:ready.set()
observer.on_message=lambda client,userdata,message:received.append(message.topic) if message.topic in tracked else None
observer.connect('127.0.0.1',1883);observer.loop_start()
assert ready.wait(4),'Broker subscription failed'
publisher=MqttClientService('127.0.0.1',1883,json.dumps)
blocked='homecontrol/cmd/tuya/Mosógép/switch'
assert not publisher.publish(blocked,{'value':False},qos=1)[0]
assert not publisher.publish('homecontrol/cmd/tuya/renamed/switch',{'entity_id':121,'value':True},qos=1)[0]
assert publisher.publish('homecontrol/cmd/tuya/hc-r5-control/switch',{'entity_id':122,'value':True},qos=1)[0]
time.sleep(0.3);observer.disconnect();observer.loop_stop()
assert received==['homecontrol/cmd/tuya/hc-r5-control/switch'],received
print(json.dumps(dict(blocked_messages_on_broker=0,control_messages_on_broker=1)))
'''

FAKE_TUYA=r'''
import json,os,runpy,sys,types
import paho.mqtt.client as mqtt
original_publish=mqtt.Client.publish
def recorded_publish(self,topic,payload=None,*args,**kwargs):
    if topic.endswith('/command_result'):
        data=json.loads(payload)
        if data.get('device_name') in ('AI-RENAMED','CONTROL'):
            with open('/probe/state/decisions.jsonl','a') as stream:stream.write(json.dumps(data)+'\n')
    return original_publish(self,topic,payload,*args,**kwargs)
mqtt.Client.publish=recorded_publish
class Device:
    def __init__(self,device_id,*args,**kwargs):self.device_id=device_id
    def set_version(self,*args):pass
    def set_socketPersistent(self,*args):pass
    def set_socketTimeout(self,*args):pass
    def status(self):return {'dps':{'1':True,'19':0,'20':2300,'18':0}}
    def set_status(self,value,dp):
        with open('/probe/state/calls.jsonl','a') as stream:
            stream.write(json.dumps({'device_id':self.device_id,'value':value,'dp':dp})+'\n')
        return {'ok':True}
stub=types.ModuleType('tinytuya');stub.Device=Device;stub.OutletDevice=Device
sys.modules['tinytuya']=stub
sys.path.insert(0,'/app')
runpy.run_path('/app/tuya_poller.py',run_name='__main__')
'''

DIRECT_CONSUMER_PROBE=r'''
import json,sys,threading,time
import paho.mqtt.client as mqtt
base=sys.argv[1];results=[];seen=[];online=threading.Event();subscribed=threading.Event()
client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
client.on_connect=lambda client,*args:client.subscribe(base+'/#',qos=1)
client.on_subscribe=lambda *args:subscribed.set()
def message(client,userdata,msg):
    seen.append(msg.topic)
    if msg.topic.endswith('/poller/availability') and msg.payload==b'online':online.set()
    if msg.topic.endswith('/command_result'):
        result=json.loads(msg.payload)
        if result.get('device_name') in ('AI-RENAMED','CONTROL'):results.append(result)
client.on_message=message;client.connect('127.0.0.1',1883);client.loop_start()
assert subscribed.wait(4) and online.wait(6),'Synthetic poller did not become ready'
for name in ('AI-RENAMED','bf1d8186d331470cafxzfz','CONTROL'):
    info=client.publish('homecontrol/cmd/tuya/'+name+'/switch',json.dumps({'value':False}),qos=1)
    info.wait_for_publish(timeout=3)
for _ in range(60):
    if len(results)>=3:break
    time.sleep(0.1)
client.disconnect();client.loop_stop()
blocked=[x for x in results if x.get('code')=='deployment_restricted']
success=[x for x in results if x.get('ok')]
print(json.dumps(dict(direct_mqtt_commands_published=3,ai_rejection_replies_received=len(blocked),
                     control_replies_received=len(success),reply_delivery_complete=len(blocked)==2 and len(success)==1)))
'''

def consumer(phase):
    folder=lab.EVIDENCE/('consumer-'+phase);folder.mkdir(mode=0o700,exist_ok=True)
    state=folder/'state';state.mkdir(mode=0o700,exist_ok=True)
    (state/'calls.jsonl').unlink(missing_ok=True)
    (state/'decisions.jsonl').unlink(missing_ok=True)
    fake=folder/'runner.py';fake.write_text(FAKE_TUYA)
    topic='homecontrol/tele/tuya-r5-'+phase
    config={'poll_seconds':0.5,'log_dir':'/tmp/tuya-log','sinks':{'console':False,'file':False,'mqtt':True},
            'mqtt':{'host':'127.0.0.1','port':1883,'base_topic':topic,'command_topic':'homecontrol/cmd/tuya'},
            'devices':[{'device_id':identity,'name':name,'device_ip':'192.0.2.1','local_key':'synthetic','dp_map':{'switch':1}}
                       for identity,name in (('bf1d8186d331470cafxzfz','AI-RENAMED'),('CONTROL-ID','CONTROL'))]}
    cfg=folder/'config.json';cfg.write_text(json.dumps(config));cfg.chmod(0o600)
    env=folder/'env';env.write_text('TUYA_CFG=/probe/config.json\nPYTHONDONTWRITEBYTECODE=1\n');env.chmod(0o600)
    manifest=json.loads((lab.RELEASE/'release.json').read_text())
    lab.container('tuya',manifest['images']['tuya'],args=('-u','/probe/runner.py'),entrypoint='python',env_file=env,
                  mounts=((fake,'/probe/runner.py:ro'),(cfg,'/probe/config.json:ro'),(state,'/probe/state')))
    try:
        result=json.loads(lab.run(['docker','exec',lab.PREFIX+'backend','python','-c',DIRECT_CONSUMER_PROBE,topic]))
        import time
        for _ in range(60):
            decisions=[json.loads(line) for line in (state/'decisions.jsonl').read_text().splitlines()] if (state/'decisions.jsonl').exists() else []
            if len(decisions)>=3:break
            time.sleep(0.1)
        assert sum(row.get('code')=='deployment_restricted' for row in decisions)==2,decisions
        assert sum(row.get('ok') is True for row in decisions)==1,decisions
        calls=[json.loads(line) for line in (state/'calls.jsonl').read_text().splitlines()]
        assert len(calls)==1 and calls[0]['device_id']=='CONTROL-ID',calls
        return {**result,'consumer_ai_rejections':2,'ai_actuator_calls':0,'control_actuator_calls':1,'real_device_transport':False}
    finally:
        import subprocess
        log=subprocess.run(['docker','logs',lab.PREFIX+'tuya'],capture_output=True,text=True)
        (folder/'poller.log').write_text(log.stdout+log.stderr)
        lab.stop('tuya')

def restrictions(phase):
    status=lab.http('/api/deployment/status')
    assert status['status']==200 and status['body']['restricted'] and status['body']['policy_valid']
    node=lab.http('/api/ai/node/status')
    assert node['status']==200 and node['body']['state']=='disabled'
    ai=lab.http('/api/ai/status');assert ai['status']==503 and ai['body']['disabled']
    for path in ('/api/ai/node/wake','/api/ai/node/command','/api/ai/chat','/api/ai/restart','/api/admin/containers/ai/restart',
                 '/api/backup/full-ai','/api/backup/gitea/status','/api/backup/gitea/commit',
                 '/api/backup/gitea/restore','/api/power-wall/command','/api/tuya/command'):
        response=lab.http(path,'POST',{'action':'shutdown','entity_id':121,'value':False})
        assert response['status']==503,(phase,path,response)
    assert lab.http('/api/process-bindings/ai_node_power_plug','PUT',{'entity_id':122})['status']==503
    assert lab.http('/api/backup/restore','POST',{'mode':'in_place','confirm':'RESTORE'})['status']==503
    assert lab.http('/api/backup/restore/recover','POST',{'confirm':'ROLLBACK'})['status']==503
    local=lab.http('/api/backup/create','POST',{})
    assert local['status']==(503 if phase=='rollback' else 202)
    if phase!='rollback':
        backup=lab.http('/api/backup')['body']
        assert backup['deployment']['restricted']
        assert all(backup['effective_settings'][key] is False for key in
                   ('restic_enabled','restic_required','git_enabled','git_offsite_enabled','ai_weekly_backup_enabled'))
    broker=json.loads(lab.run(['docker','exec',lab.PREFIX+'backend','python','-c',BROKER_PROBE]))
    actuator=consumer(phase)
    checks.append(dict(phase=phase,ai_routes_blocked=True,ai_binding_frozen=True,
                       ai_health='disabled',local_backup_http_status=local['status'],**broker,consumer=actuator))
    print('Restricted API/broker guards passed: '+phase,flush=True)

if __name__=='__main__':
    checks=[]
    lab.main(after_phase=restrictions)
    report=dict(ok=True,phases=checks,physical_commands=False,production_changed=False,
                real_systemd_manager=False,real_empty_vm_restore=False)
    (lab.EVIDENCE/'restricted-runtime-results.json').write_text(json.dumps(report,indent=2)+'\n')
