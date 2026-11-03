import json
from pathlib import Path
import subprocess
import time

ROOT=Path('/srv/docker/homecontrol')
OUT=ROOT/'backups/releases/hc-audit-20261103-r22/evidence'
WORK=Path('/tmp/hc-r20-process-fixture')
WORK.mkdir(exist_ok=True)
config={'devices':[{'device_id':'fixture-id','device_ip':'192.0.2.10','local_key':'0000000000000000','device_name':'fixture'}],
        'sinks':{'console':False,'file':False,'mqtt':True}, 'poll_seconds':.2,
        'fast_timeout':.05,'slow_timeout':.05,'max_workers':1,'log_dir':'/tmp/tuya',
        'cooldown_connect_sec':1,'cooldown_generic_sec':1,'cooldown_keyver_sec':1}
(WORK/'tuya.json').write_text(json.dumps(config))
lock=json.loads((OUT/'candidate-image-lock.json').read_text())
builds={n:{'image':lock['homecontrol-'+n]} for n in ('backend','ha-growatt-poller')}
envs={'backend':{},'tuya-poller':{'TUYA_CFG':'/fixture/tuya.json','MQTT_HOST':'127.0.0.1','MQTT_PORT':'9'},
      'gree-climate':{'MQTT_HOST':'127.0.0.1','MQTT_PORT':'9','GREE_CLIMATE_IP':'192.0.2.11','GREE_CLIMATE_POLL_SECONDS':'5','GREE_COMMAND_TIMEOUT':'.1','GREE_BUZZER_SETTINGS_PATH':'/tmp/buzzer.json'},
      'xiaomi-x10':{'X10_MQTT_HOST':'127.0.0.1','X10_MQTT_PORT':'9','X10_ROBOT_TOKEN':'','X10_MAP_OUTPUT_DIR':'/tmp/maps'},
      'ha-growatt-poller':{'MQTT_HOST':'127.0.0.1','MQTT_PORT':'9','HA_BASE_URL':'http://127.0.0.1:9','HA_TOKEN':'fixture',
          'HA_GROWATT_ENTITY_MAP':'{"power":"sensor.fixture"}','HA_GROWATT_POLL_SECONDS':'.2','HA_GROWATT_REQUEST_TIMEOUT_SECONDS':'.1'},
      'ingest':{},'ai-server':{'AI_CONFIG_PATH':'/tmp/ai.json','AI_PROVIDER':'ollama','OLLAMA_URL':'http://127.0.0.1:9'}}
envs={k:v for k,v in envs.items() if k in ('backend','ha-growatt-poller')}
names=[]
def command(args,timeout=30):
    return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
http="""import urllib.request,urllib.error,json
out={}
for path in PATHS:
 try:
  with urllib.request.urlopen('http://127.0.0.1:PORT'+path,timeout=2) as response:out[path]=response.status
 except urllib.error.HTTPError as e:out[path]=e.code
 except Exception as e:out[path]=type(e).__name__
print(json.dumps(out))
"""
results={}
try:
    for component,env in envs.items():
        name='hc22-process-'+component
        if command(['docker','container','inspect',name]).returncode==0:
            raise RuntimeError('refusing preexisting lab container: '+name)
        args=['docker','run','-d','--name',name,'--label','hc.audit=hc22-process','--network','none','--read-only','--user','1000:1000',
              '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--memory','256m',
              '--tmpfs','/tmp:rw,exec,nosuid,nodev,size=128m','-e','PYTHONDONTWRITEBYTECODE=1',
              '--mount',f'type=bind,src={WORK},dst=/fixture,readonly']
        for key,value in env.items():args+=['-e',key+'='+value]
        args.append(builds[component]['image'])
        result=command(args)
        if result.returncode:raise RuntimeError(component+' could not start')
        names.append(name)
    # Bounded laboratory startup wait, not a production maintenance pause.
    time.sleep(12)
    for component in envs:
        name='hc22-process-'+component
        state=json.loads(command(['docker','inspect',name]).stdout)[0]['State']
        row={'running':state['Running'],'exit_code':state['ExitCode']}
        if row['running']:
            if component in ('backend','ai-server'):
                port=5000 if component=='backend' else 8088
                code=http.replace('PATHS',repr(['/health/live','/health/ready','/health/workers'] if component=='backend' else ['/health/live','/health/ready'])).replace('PORT',str(port))
                result=command(['docker','exec',name,'python','-B','-c',code])
                row['http']=json.loads(result.stdout) if result.returncode==0 else {'probe_exit':result.returncode}
            else:
                script='ingest_healthcheck.py' if component=='ingest' else 'worker_health.py'
                for mode in ('live','ready'):
                    row[mode+'_exit']=command(['docker','exec',name,'python','-B',script,'--mode',mode]).returncode
        results[component]=row
        (WORK/(component+'-process.log')).write_text(command(['docker','logs',name]).stdout+command(['docker','logs',name]).stderr)
    (OUT/'process-lab.json').write_text(json.dumps({'network':'none','published_ports':0,'hardware_contacted':False,'results':results},indent=2)+'\n')
    print(json.dumps(results,indent=2),flush=True)
finally:
    for name in names:command(['docker','rm','-f',name])
expected=all(row['running'] and (row.get('live_exit')==0 and row.get('ready_exit')==1
           if 'live_exit' in row else row.get('http',{}).get('/health/live')==200 and row.get('http',{}).get('/health/ready')==503)
           for row in results.values())
if not expected:raise SystemExit(1)
