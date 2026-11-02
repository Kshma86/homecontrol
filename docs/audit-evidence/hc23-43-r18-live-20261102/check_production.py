"""Read-only r18 post-deployment check; no secrets, restarts or remote writes."""
from datetime import datetime, timezone
import hashlib,json,subprocess,urllib.request,urllib.error
from pathlib import Path

B=Path('/srv/docker/homecontrol');NAME='hc-security-20261102-r18';K=B/'backups/releases'/NAME
OUT=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def command(args):return subprocess.check_output(args,text=True,timeout=30)
def require(value,message):
 if not value:raise ValueError(message)
def request(path):
 with urllib.request.urlopen('http://127.0.0.1:5000'+path,timeout=10) as response:return json.load(response)

m=read(K/'release.json');marker=read(B/'infra/access-release.json');live=read(K/'evidence/router-live-acceptance.json')
require(marker['release']==NAME and live['ok'],'Wrong active release')
run=read(B/'backups/runs'/(live['run_id']+'.json'))
require(run['state']=='completed' and run['returncode']==0 and not run.get('missing_required_targets'),'Backup incomplete')
require(all(run['targets'][k]['state']=='succeeded' for k in (*run['required_targets'],'restic_retention')),'Required backup target failed')
changed={}
for root in (K/'source',Path(marker['runtime'])):
 changed[str(root)]=[n for n,h in m['source_sha256'].items() if not (root/n).is_file() or sha(root/n)!=h]
require(not any(changed.values()),'Sealed source/runtime drift')
require(sha(K/'evidence/acceptance.json')==m['acceptance_sha256'],'Offline acceptance changed')
accepted=read(K/'evidence/acceptance.json')
require(all(sha(K/'evidence'/n)==h for n,h in accepted['evidence_sha256'].items()),'Sealed evidence changed')
require(sha(B/'HC_REFACTOR_AUDIT.md')=='51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2','Original audit changed')
containers={}
expected={('zigbee2mqtt' if s=='zigbee2mqtt' else 'homecontrol-'+('ingest' if s=='hc_ingest' else s.removeprefix('homecontrol-'))):image for s,image in m['images'].items()}
expected['homeassistant']=m['homeassistant_image']
fmt='{"id":{{json .Id}},"image":{{json .Image}},"running":{{json .State.Running}},"health":{{with index .State "Health"}}{{json .Status}}{{else}}null{{end}},"restarts":{{json .RestartCount}}}'
for name in m['baseline']:
 row=json.loads(command(['docker','inspect','--format',fmt,name]));containers[name]=row
 if name in expected:require(row['running'] and row['image']==expected[name],'Container mismatch: '+name)
 else:require(row['id']==m['baseline'][name]['id'] and row['image']==m['baseline'][name]['image'],'Unchanged container changed')
for service in m['health_required']:
 name='zigbee2mqtt' if service=='zigbee2mqtt' else 'homecontrol-'+('ingest' if service=='hc_ingest' else service.removeprefix('homecontrol-'))
 require(containers[name]['health']=='healthy','Health pending: '+name)
health={path:{'ok':request(path).get('ok')} for path in ('/health','/health/live','/health/ready','/health/workers')}
require(all(row['ok'] is True for row in health.values()),'Backend health failed')
web={}
for port in (80,3000):
 with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/',timeout=10) as response:
  html=response.read();web[str(port)]={'status':response.status,'html':b'<html' in html,'built_assets':b'/assets/' in html}
 require(web[str(port)]['status']==200 and web[str(port)]['html'] and web[str(port)]['built_assets'],'Web frontend failed')
robot=request('/api/xiaomi-x10/state');robot={k:robot[k] for k in ('robot_state','online','is_online') if k in robot}
timers={}
for name in ('homecontrol-backup.timer','homecontrol-ai-weekly-backup.timer','homecontrol-restic-check.timer','homecontrol-log-maintenance.timer','homecontrol-post-boot-health.timer'):
 data=dict(line.split('=',1) for line in command(['systemctl','show',name,'-p','ActiveState','-p','UnitFileState','-p','NextElapseUSecRealtime','-p','NextElapseUSecMonotonic']).splitlines() if '=' in line)
 require(data['ActiveState']=='active' and data['UnitFileState']=='enabled','Timer not enabled: '+name);timers[name]=data
failed=command(['systemctl','--failed','--no-legend','--plain','--no-pager']).strip().splitlines()
require(not failed,'Failed systemd units')
services={name:command(['systemctl','show',name,'-p','ActiveState','--value']).strip() for name in ('homecontrol-hostops.service','homecontrol-mqtt-access.service')}
require(all(v=='active' for v in services.values()),'Host guard not active')
ha=read(K/'evidence/ha-live-acceptance.json');pg=read(K/'evidence/postgres-live-acceptance.json');probe=read(K/'evidence/ha-full-private-preflight.json')
require(ha['ok'] and ha['authenticated_api'] and ha['image']==m['homeassistant_image'],'HA gate failed')
require(pg['ok'] and pg['major']==16 and pg['recorded']==pg['actual'],'PostgreSQL gate failed')
require(probe['ok'] and probe['rows_preserved'],'Full protected HA preflight failed')
require(live['ai_enabled'] is False,'AI must remain disabled')
receipt=run['archive']
result={'ok':True,'checked_at':datetime.now(timezone.utc).isoformat(),'release':NAME,'live_acceptance':live,
 'backup':{'state':run['state'],'returncode':run['returncode'],'targets':{k:v['state'] for k,v in run['targets'].items()},'archive':receipt,
 'archive_verification':'Root activation verified archive bytes and restored PostgreSQL; the protected archive was not re-read by this operator check.'},
 'sealed_file_count':len(m['source_sha256']),'changed_files':changed,'sealed_evidence_verified':True,
 'containers':containers,'pinned_running_components':len(expected),'health':health,'web':web,'robot':robot,
 'timers':timers,'services':services,'systemd_failed':failed,'homeassistant':ha,'postgres':pg,'full_private_ha_preflight':probe,
 'ai_enabled':False,'remote_write_commands':0,'services_restarted':False}
(OUT/'production-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'ok':True,'release':NAME,'sealed_files':len(m['source_sha256']),'running_components':len(expected),'timers':len(timers),'growatt_entities':ha['previously_available_growatt_entities_preserved'],'verified_archive_files':receipt['verified_files']}))
