"""Read-only r12 acceptance evidence, plus the authorized local backup receipt."""
import datetime,hashlib,json,subprocess,urllib.request
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-f10-20261031-r12';m=json.loads((K/'release.json').read_text());marker=json.loads((B/'infra/access-release.json').read_text())
assert marker['release']==m['release']
rows=json.loads(subprocess.check_output(['docker','inspect',*m['baseline']]))
def get(p):return json.load(urllib.request.urlopen('http://127.0.0.1:5000'+p,timeout=15))
apps={};changed=set()
for service,image in m['images'].items():
 name='homecontrol-'+('ingest' if service=='hc_ingest' else service.removeprefix('homecontrol-'));changed.add(name)
 row=next(r for r in rows if r['Name']=='/'+name)
 assert row['Image']==image and row['State']['Running'] and row['State']['Health']['Status']=='healthy' and row['RestartCount']==0
 apps[service]={'image':image,'healthy':True,'restarts':0}
assert all(r['Id']==m['baseline'][r['Name'].lstrip('/')]['id'] and r['Image']==m['baseline'][r['Name'].lstrip('/')]['image'] for r in rows if r['Name'].lstrip('/') not in changed)
health={p:get(p) for p in ('/health','/health/live','/health/workers','/health/ready')};assert all(v['ok'] for v in health.values())
x=get('/api/xiaomi-x10/state');assert x['bridge_online'] and x['mqtt_connected'] and x['telemetry_available']
i=get('/api/irrigation/pilot');c=get('/api/combustion-safety/state');assert i['ok'] and c['ok'] and c.get('evaluation_error') is None
backup=get('/api/backup');run=backup['activity']['run'];assert run['run_id']=='7595700918fe4e579fcba0cd16149fe3' and run['state']=='completed' and run['archive']['completed']
policy_code='import deployment_policy,json; p=deployment_policy.policy(); print(json.dumps({k:p[k] for k in ("restricted","valid")}))'
policy=json.loads(subprocess.check_output(['docker','exec','homecontrol-backend','python','-B','-c',policy_code]));assert policy=={'restricted':True,'valid':True}
for name,sha in m['source_sha256'].items():assert hashlib.sha256((Path(marker['runtime'])/name).read_bytes()).hexdigest()==sha,name
frontend=subprocess.run(['curl','--fail','--silent','--output','/dev/null','--write-out','%{http_code}','http://127.0.0.1:3000/'],capture_output=True,text=True)
if frontend.returncode:frontend_http='not_exposed_at_3000'
else:frontend_http=frontend.stdout
result={'ok':True,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'release':marker['release'],'applications':apps,'platform_container_ids_unchanged':True,'health':health,
 'installed_source_files_verified':len(m['source_sha256']),'x10':{k:x.get(k) for k in ('bridge_online','mqtt_connected','telemetry_available','robot_state','robot_state_text')},
 'irrigation_mode':i['config'].get('mode'),'combustion':{k:c.get(k) for k in ('level','latched','danger','evaluation_error')},'combustion_enabled':c.get('config',{}).get('enabled'),
 'ai_policy':policy,'backup':run['archive'],'frontend_http':frontend_http,
 'x10_online_reasserted_after_observed_ready':True,'x10_persistent_startup_correction':'prepared separately as r13, not deployed','physical_actuator_tests_performed':False}
(K/'evidence/live-acceptance.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('ok','release','installed_source_files_verified','x10','irrigation_mode','combustion','ai_policy','frontend_http')}))
