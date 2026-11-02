#!/usr/bin/env python3
"""Read-only public deployment, content and scheduler acceptance."""
from datetime import datetime, timezone
import hashlib,json,subprocess,urllib.request
from pathlib import Path
B=Path('/srv/docker/homecontrol'); N='hc-router-backup-20261101-r16'
K=B/'backups/releases'/N; OUT=Path(__file__).resolve().parent
m=json.loads((K/'release.json').read_text())
a=json.loads((K/'evidence/acceptance.json').read_text())
live=json.loads((K/'deployment-status.json').read_text())
marker=json.loads((B/'infra/access-release.json').read_text())
assert marker['release']==N and live['ok'] and live['audit_input_prepared']
changed={}
for root in (K/'source',Path(marker['runtime'])):
 changed[str(root)]=[n for n,h in m['source_sha256'].items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
assert not any(changed.values())
assert hashlib.sha256((K/'evidence/acceptance.json').read_bytes()).hexdigest()==m['acceptance_sha256']
assert all(hashlib.sha256((K/'evidence'/n).read_bytes()).hexdigest()==h for n,h in a['evidence_sha256'].items())
state=json.loads((B/'backups/backup-state.json').read_text())
assert state['run_id']==live['run_id'] and state['state']=='completed' and not state['missing_required_targets']
assert all(state['targets'][t]['state']=='succeeded' for t in (*state['required_targets'],'restic_retention'))
def api(path):
 return json.load(urllib.request.urlopen('http://127.0.0.1:5000'+path,timeout=10))
health=api('/health'); policy=api('/api/deployment/status')
readiness=api('/health/ready')
assert health['db_ok'] and health['mqtt_ok'] and readiness['ok']
assert policy['ai_enabled'] is False and policy['router_backup_enabled'] is True
containers={}
for name in m['baseline']:
 x=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
 containers[name]={'id':x['Id'],'image':x['Image'],'running':x['State']['Running'],'health':x['State'].get('Health',{}).get('Status')}
for service in ('backend','frontend'):
 assert containers['homecontrol-'+service]['image']==m['images'][service]
 assert containers['homecontrol-'+service]['health']=='healthy'
unchanged=all(containers[n]['id']==v['id'] and containers[n]['image']==v['image'] for n,v in m['baseline'].items() if n not in ('homecontrol-backend','homecontrol-frontend'))
assert unchanged
names=['homecontrol-backup.timer','homecontrol-ai-weekly-backup.timer','homecontrol-restic-check.timer','homecontrol-log-maintenance.timer','homecontrol-post-boot-health.timer']
timers={}
for name in names:
 txt=subprocess.check_output(['systemctl','show',name,'--property=ActiveState,UnitFileState,NextElapseUSecRealtime,NextElapseUSecMonotonic'],text=True)
 data=dict(line.split('=',1) for line in txt.splitlines())
 assert data['ActiveState']=='active' and data['UnitFileState']=='enabled'
 assert any(data.get(n,'') not in ('','0','n/a','infinity') for n in ('NextElapseUSecRealtime','NextElapseUSecMonotonic'))
 timers[name]=data
failed=subprocess.check_output(['systemctl','--failed','--no-legend','--plain'],text=True).strip().splitlines();assert not failed
old=json.loads((B/'backups/releases/hc-router-backup-20261101-r15/release.json').read_text())
assert all(hashlib.sha256((B/'backups/releases/hc-router-backup-20261101-r15/source'/n).read_bytes()).hexdigest()==h for n,h in old['source_sha256'].items())
audit=hashlib.sha256((B/'HC_REFACTOR_AUDIT.md').read_bytes()).hexdigest();assert audit=='51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2'
r=dict(ok=True,checked_at=datetime.now(timezone.utc).isoformat(),release=N,live_acceptance=live,backup_state=state,sealed_file_count=len(m['source_sha256']),changed_files=changed,sealed_acceptance_evidence_unchanged=True,old_r15_sealed_source_unchanged=True,original_audit_sha256=audit,health=health,readiness=readiness,policy=policy,containers=containers,unchanged_platform=unchanged,timers=timers,systemd_failed=failed,remote_write_commands=0)
(OUT/'production-check.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'ok':True,'sealed_files':len(m['source_sha256']),'timers':len(timers),'platform_unchanged':unchanged,'ai_enabled':False}))
