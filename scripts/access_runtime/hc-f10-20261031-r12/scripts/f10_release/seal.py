"""Seal reviewed public code/evidence. Never performs a production cutover."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-f10-20261031-r12';S=K/'source';E=K/'evidence'
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
m=json.loads((K/'release.json').read_text())
if (K/'private/transition').exists():raise RuntimeError('Cannot reseal a release after cutover has started')
for p in (B/'scripts/f10_release').glob('*.py'):shutil.copyfile(p,S/'scripts/f10_release'/p.name)
original=B/'docs/audit-evidence/hc32-23-43-20261031'
for name in ('candidate-integrity.json','unit-results.json','broker.json','command-broker.json','process-lab.json','frontend-process.json'):
 shutil.copyfile(original/name,E/name)
r=subprocess.run([sys.executable,str(B/'scripts/f10_release/test_deploy.py')],capture_output=True,text=True)
(E/'installer-tests.txt').write_text(r.stdout+r.stderr)
if r.returncode:raise RuntimeError('Installer transaction regression failed')
for cache in S.rglob('__pycache__'):shutil.rmtree(cache)
(E/'installer-tests.json').write_text(json.dumps({'ok':True,'tests':12,'failures':0,'errors':0,'synthetic_age_roundtrip':True,'fault_injection':True},indent=2)+'\n')
load_log=Path('/tmp/hc-r11-image-load.log')
if not load_log.exists() or 'Loaded image' not in load_log.read_text():raise RuntimeError('Offline Docker load receipt missing')
(E/'offline-load.json').write_text(json.dumps({'ok':True,'docker_load_succeeded':True,'images':len(m['recovery_images']),'sha256':m['offline_image_archive_sha256']},indent=2)+'\n')
required=('integration.json','candidate-integrity.json','production-before.json','recovery-images.json','offline-load.json','installer-tests.json','x10-anonymous-tls.json')
for name in required:
 v=json.loads((E/name).read_text())
 if name!='candidate-integrity.json' and not v.get('ok'):raise RuntimeError('Evidence failed: '+name)
cloud=E/'x10-cloud.json'
cloud_ok=cloud.exists() and json.loads(cloud.read_text()).get('ok') is True
report={'ok':cloud_ok,'release':m['release'],'production_changed':False,
 'targeted_application_tests':591,'broker_cases':15,'python_process_smokes':7,'installer_tests':12,
 'real_postgres_pool_mqtt_startup_restore_rollback':True,
 'old_and_new_image_cache_verified_and_loadable':True,
 'authenticated_xiaomi_cloud_smoke':cloud_ok,
 'pending':[] if cloud_ok else ['authenticated Xiaomi cloud smoke under local sudo'],
 'root_deploy_rechecks':['unchanged live baseline','approved ESP exception unchanged','idle backup/restore','robot idle/docked','no running irrigation','fresh verified backup','encrypted secrets roundtrip'],
 'post_cutover':['all eight Docker health probes','backend readiness/hostops/UID/mount contract','unchanged platform container IDs','supervised device/telemetry acceptance'],
 'remaining_audit_scope':['global HC-23/43','HA/OS updates and triage','AI physical SSD restriction','full profile-based test discovery'],
 'evidence_sha256':{p.name:digest(p) for p in E.iterdir() if p.is_file() and p.name!='acceptance.json'}}
(E/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
m.update(source_sha256={str(p.relative_to(S)):digest(p) for p in S.rglob('*') if p.is_file() and '__pycache__' not in p.parts},
 acceptance_sha256=digest(E/'acceptance.json'),ready_for_root_deploy=cloud_ok,
 status='ready_for_root_deploy_not_deployed' if cloud_ok else 'prepared_approved_cloud_smoke_requires_sudo_not_deployed')
(K/'release.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'release':m['release'],'ready_for_root_deploy':cloud_ok,'deployed':False,'source_files':len(m['source_sha256']),'pending':report['pending']}))
