from pathlib import Path
import subprocess,json,sys,shutil,tarfile
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-router-backup-20261101-r16';S=K/'source'
sys.path.insert(0,str(B/'scripts/access_release'));from prepare import pin_network_addresses;from common import SERVICES,write_json
network=json.loads(subprocess.check_output(['docker','network','inspect','homecontrol_default'],text=True))[0]
ids=list(network['Containers'])
rows=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True));rows={r['Config']['Labels']['com.docker.compose.service']:r for r in rows}
model=json.loads((S/'runtime.compose.json').read_text());rollback=json.loads((K/'private/rollback.compose.json').read_text())
endpoints=pin_network_addresses(model,rows,network);pin_network_addresses(rollback,rows,network)
write_json(S/'runtime.compose.json',model,0o644);write_json(K/'private/rollback.compose.json',rollback)
v=json.loads((K/'release.json').read_text());v['network']['fixed_endpoints']=endpoints
v['previous_images'].update({s:r['Image'] for s,r in rows.items() if s in SERVICES})
v['required_container_recreates']=list(SERVICES)
write_json(K/'release.json',v,0o644)
for p in (B/'scripts/access_release').glob('*.py'):shutil.copyfile(p,S/'scripts/access_release'/p.name)
shutil.copyfile(B/'infra/backend/tests/test_access_release.py',S/'infra/backend/tests/test_access_release.py')
W=Path('/tmp/hc-vm-20261030');R='scripts/access_runtime/hc-router-backup-20261101-r16'
with tarfile.open(W/'private/network-boot-fix.tar','w') as t:
 for name in ('runtime.compose.json','scripts/access_release/common.py','scripts/access_release/prepare.py','scripts/access_release/install.py'):
  t.add(S/name,arcname='srv/docker/homecontrol/'+R+'/'+name)
  t.add(S/name,arcname='lab/project/'+R+'/'+name)
  t.add(S/name,arcname='lab/project/'+name)
print(json.dumps({'fixed_endpoints':endpoints,'container_recreates':list(SERVICES)}))
