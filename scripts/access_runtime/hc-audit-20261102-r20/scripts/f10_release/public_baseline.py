"""Read-only production baseline. Never collect environment or credentials."""
import hashlib,json,subprocess,urllib.request
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-audit-20261102-r20'
m=json.loads((K/'release.json').read_text())
rows=json.loads(subprocess.check_output(['docker','inspect',*m['baseline']]))
assert all(m['baseline'][r['Name'].lstrip('/')]=={'id':r['Id'],'image':r['Image']} for r in rows)
def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:5000'+path,timeout=10))
health=get('/health');assert health.get('db_ok') and health.get('mqtt_ok') and health.get('ok')
x10=get('/api/xiaomi-x10/state')
assert str(x10.get('robot_state')) in ('6','13')
b=get('/api/backup')['activity']['run'];assert b['state']=='completed' and b['archive']['completed']
# The same quiescence query is used under root immediately before deployment.
from deploy import guard_runtime
sql="SELECT (SELECT count(*) FROM hc.irrigation_manual_session WHERE status IN ('starting','running','stop_failed')) + (SELECT count(*) FROM hc.irrigation_solar_pump_run WHERE status='running');"
r=subprocess.run(['docker','exec','-i','homecontrol-postgres','sh','-c','exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],input=sql,text=True,capture_output=True,check=True)
assert r.stdout.strip()=='0'
original=json.loads((B/'backups/releases/hc-access-20261030-r10/release.json').read_text())
source=original.get('source_sha256',{})
for name,sha in source.items():assert hashlib.sha256((B/'scripts/access_runtime/hc-access-20261030-r10'/name).read_bytes()).hexdigest()==sha,name
result={'ok':True,'active_release':json.loads((B/'infra/access-release.json').read_text())['release'],
 'all_container_ids_and_images_unchanged':True,'containers':len(rows),'running':sum(r['State']['Running'] for r in rows),
 'health':{k:health.get(k) for k in ('ok','db_ok','mqtt_ok')},'x10_robot_state':x10.get('robot_state'),
 'active_irrigation_sessions':0,'backup':{k:b['archive'][k] for k in ('name','sha256','size_bytes','verified_files','timestamp')},
 'old_frozen_source_hashes_checked':len(source),'audit_sha256':hashlib.sha256((B/'HC_REFACTOR_AUDIT.md').read_bytes()).hexdigest()}
(K/'evidence/production-before.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
