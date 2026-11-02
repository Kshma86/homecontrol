"""Read-only r18 drift check; never expose container environment or secrets."""
import hashlib,json,subprocess
from pathlib import Path
from datetime import datetime,timezone
BASE=Path('/srv/docker/homecontrol');OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
marker=json.loads((BASE/'infra/access-release.json').read_text());name=marker['release']
assert name=='hc-security-20261102-r18'
release=json.loads((BASE/'backups/releases'/name/'release.json').read_text())
runtime=BASE/'scripts/access_runtime'/name
bad=[p for p,h in release['source_sha256'].items() if not (runtime/p).is_file() or sha(runtime/p)!=h]
previous=json.loads((BASE/'docs/audit-evidence/hc26-20261102/production-unchanged.json').read_text())['containers']
rows=json.loads(subprocess.check_output(['docker','inspect',*previous],text=True))
current={r['Name'].lstrip('/'):{'id':r['Id'],'image':r['Image'],'running':r['State']['Running']} for r in rows}
assert not bad and len(release['source_sha256'])==736 and current==previous
before=json.loads((OUT/'before.json').read_text());pending_bad=[]
current_task_docs={'AUDIT_REPAIR.md','DEPLOYMENT_PREP.md','docs/hc23-43-platform-release-20261102.md'}
for p,info in before['pending_changes'].items():
 if p in current_task_docs:continue
 path=BASE/p
 if (info['state']=='deleted' and path.exists()) or (info['state']!='deleted' and (not path.is_file() or sha(path)!=info['sha256'])):pending_bad.append(p)
assert not pending_bad,pending_bad
prior_bad=[]
for task,files in before['prior_evidence_manifests'].items():
 for p,h in files.items():
  path=BASE/'docs/audit-evidence'/(task+'-20261102')/p
  if not path.is_file() or sha(path)!=h:prior_bad.append(str(path))
assert not prior_bad,prior_bad
assert sha(BASE/'HC_REFACTOR_AUDIT.md')==before['audit_sha256']
result={'ok':True,'checked_at':datetime.now(timezone.utc).isoformat(),'active_release':name,
 'runtime_source_count':len(release['source_sha256']),'runtime_drift':bad,
 'production_containers_unchanged':True,'containers':current,'production_deploy_or_restart':False,
 'pending_source_fingerprints_preserved':len(set(before['pending_changes'])-current_task_docs),
 'prior_evidence_files_preserved':sum(map(len,before['prior_evidence_manifests'].values())),
 'original_audit_sha256':before['audit_sha256'],'live_mqtt_publish_commands':0,'live_db_queries':0}
(OUT/'production-unchanged.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='containers'}))
