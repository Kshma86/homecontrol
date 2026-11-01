"""Create a separate r12 kit after verified recovery. Do not touch r11 history."""
import hashlib,json,shutil,subprocess
from pathlib import Path
B=Path('/srv/docker/homecontrol');O=B/'backups/releases/hc-f10-20261031-r11'
NAME='hc-f10-20261031-r12';K=B/'backups/releases'/NAME;S=K/'source'
if K.exists():raise RuntimeError('Retry kit already exists; do not overwrite')
marker=json.loads((B/'infra/access-release.json').read_text())
assert marker['release']=='hc-access-20261030-r10'
m=json.loads((O/'release.json').read_text())
rows=json.loads(subprocess.check_output(['docker','inspect',*m['baseline']]))
assert all(r['Image']==m['baseline'][r['Name'].lstrip('/')]['image'] for r in rows)
assert all(r['State']['Running'] for r in rows if r['Name']!='/homecontrol-adminer')
shutil.copytree(O/'source',S,ignore=shutil.ignore_patterns('__pycache__'))
# Recovery belongs to the preserved r11 incident, never to the clean new attempt.
(S/'scripts/f10_release/recover.py').unlink(missing_ok=True)
for file in S.rglob('*'):
 if file.is_file() and file.suffix in ('.py','.sh','.service','.timer','.path','.conf','.json'):
  text=file.read_text()
  if 'hc-f10-20261031-r11' in text:file.write_text(text.replace('hc-f10-20261031-r11',NAME))
for name in ('deploy.py','activate.py','cloud_smoke.py','test_deploy.py'):
 text=(B/'scripts/f10_release'/name).read_text().replace('hc-f10-20261031-r11',NAME).replace('r11','r12')
 (S/'scripts/f10_release'/name).write_text(text)
(K/'private').mkdir(mode=0o700);(K/'evidence').mkdir()
shutil.copyfile(O/'private/access-images.tar.gz',K/'private/access-images.tar.gz');(K/'private/access-images.tar.gz').chmod(0o600)
for name in ('integration.json','candidate-integrity.json','unit-results.json','broker.json','command-broker.json','process-lab.json','frontend-process.json','recovery-images.json','offline-load.json','x10-anonymous-tls.json','x10-cloud.json','xiaomi-approval.json'):
 shutil.copyfile(O/'evidence'/name,K/'evidence'/name)
m.update(release=NAME,deployed=False,ready_for_root_deploy=False,status='corrected_retry_prepared_not_deployed',
 baseline={r['Name'].lstrip('/'):{'id':r['Id'],'image':r['Image']} for r in rows},
 previous_compose_sha256=hashlib.sha256((B/'infra/docker-compose.yml').read_bytes()).hexdigest(),
 retry_of='hc-f10-20261031-r11',source_sha256={},acceptance_sha256=None)
(K/'release.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'release':NAME,'same_verified_application_images':True,'production_changed':False}))
