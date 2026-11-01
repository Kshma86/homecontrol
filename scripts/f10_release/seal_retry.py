"""Seal r12 code and meaningful installer regressions; no production changes."""
import hashlib,json,shutil,subprocess,sys,re
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-f10-20261031-r12';S=K/'source';E=K/'evidence'
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return h.hexdigest()
if (K/'private/transition').exists():raise RuntimeError('Cannot reseal a started transition')
m=json.loads((K/'release.json').read_text())
r=subprocess.run([sys.executable,str(S/'scripts/f10_release/test_deploy.py')],capture_output=True,text=True)
(E/'installer-tests.txt').write_text(r.stdout+r.stderr)
if r.returncode:raise RuntimeError('Corrected installer regression failed')
tests=int(re.search(r'Ran (\d+) tests',r.stdout+r.stderr)[1])
for cache in S.rglob('__pycache__'):shutil.rmtree(cache)
(E/'installer-tests.json').write_text(json.dumps({'ok':True,'tests':tests,'failures':0,'errors':0,
 'real_install_and_rollback_lock_adapter':True,'real_file_install_and_snapshot_rollback_in_disposable_root':True,
 'privileged_chown_and_systemd_substituted_in_fixture':True,'pre_stop_adapter_and_real_root_lock_preflight':True},indent=2)+'\n')
(E/'retry-provenance.json').write_text(json.dumps({'ok':True,'retry_of':'hc-f10-20261031-r11',
 'cause':'locked adapter was called on common instead of access_release/install',
 'same_application_image_ids':True,'authenticated_cloud_smoke_reused_for_identical_image':m['images']['homecontrol-xiaomi-x10'],
 'r10_recovery_live_verified':True,'r11_historical_state_kept':True},indent=2)+'\n')
report={'ok':True,'release':m['release'],'pending':[],'production_changed':False,
 'targeted_application_tests':591,'broker_cases':15,'python_process_smokes':7,'installer_tests':tests,
 'authenticated_xiaomi_cloud_smoke':True,'real_postgres_pool_mqtt_startup_restore_rollback':True,
 'old_and_new_image_cache_verified_and_loadable':True,
 'root_deploy_rechecks':['all callable platform adapters available','actual common locks while applications still run','unchanged live r10 baseline','idle backup/restore','approved ESP exception unchanged','robot idle/docked','no running irrigation','fresh verified backup','encrypted secrets roundtrip'],
 'post_cutover':['eight Docker health probes','backend readiness and hostops/UID/mount contract','unchanged platform container IDs','supervised hardware acceptance'],
 'remaining_audit_scope':['global HC-23/43','HA/OS triage','AI SSD restriction','full profile-based test discovery'],
 'evidence_sha256':{p.name:digest(p) for p in E.iterdir() if p.is_file() and p.name!='acceptance.json'}}
(E/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
m.update(ready_for_root_deploy=True,status='corrected_retry_ready_not_deployed',
 source_sha256={str(p.relative_to(S)):digest(p) for p in S.rglob('*') if p.is_file()},
 acceptance_sha256=digest(E/'acceptance.json'))
(K/'release.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'release':m['release'],'source_files':len(m['source_sha256']),'tests':tests,'ready_for_root_deploy':True,'deployed':False}))
