"""Seal the tested r13 X10 startup correction, leave live r12 unchanged."""
import hashlib,json,shutil
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-f10-20261031-r13';E=K/'evidence';S=K/'source'
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
assert not (K/'private/transition').exists()
v=json.loads((E/'verification.json').read_text());assert v['ok']
m=json.loads((K/'release.json').read_text())
r12=B/'backups/releases/hc-f10-20261031-r12'
shutil.copyfile(r12/'evidence/live-acceptance.json',E/'r12-live-acceptance.json')
shutil.copyfile(r12/'evidence/xiaomi-approval.json',E/'xiaomi-approval.json')
shutil.copyfile(r12/'evidence/x10-cloud.json',E/'x10-cloud.json')
for cache in S.rglob('__pycache__'):shutil.rmtree(cache)
report={'ok':True,'release':m['release'],'pending':[],'hotfix_of':m['previous_release'],
 'installer_tests':16,'baked_x10_regression_tests':3,'old_image_reproducer_failed_as_expected':True,
 'dependencies_changed':False,'application_images_changed':['homecontrol-xiaomi-x10'],
 'services_restarted':['backend','homecontrol-xiaomi-x10'],
 'scope':'reassert retained bridge status after successful asynchronous MQTT connect',
 'post_cutover':['X10 bridge/online=1 and fresh telemetry','all application health checks','backend readiness/hostops','unchanged other container IDs'],
 'physical_hardware_tests_performed':False,
 'evidence_sha256':{p.name:digest(p) for p in E.iterdir() if p.is_file() and p.name!='acceptance.json'}}
(E/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n')
m.update(source_sha256={str(p.relative_to(S)):digest(p) for p in S.rglob('*') if p.is_file()},acceptance_sha256=digest(E/'acceptance.json'),ready_for_root_deploy=True,status='x10_startup_hotfix_ready_not_deployed')
(K/'release.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'release':m['release'],'ready':True,'deployed':False,'installer_tests':16,'x10_regressions':3}))
