"""Prepare r13 from live r12: X10 startup indication fix, unchanged dependencies."""
import gzip,hashlib,json,os,shutil,subprocess
from pathlib import Path
B=Path('/srv/docker/homecontrol');O=B/'backups/releases/hc-f10-20261031-r12';NAME='hc-f10-20261031-r13';K=B/'backups/releases'/NAME
if K.exists():raise RuntimeError('Do not overwrite an existing hotfix kit')
m=json.loads((O/'release.json').read_text());marker=json.loads((B/'infra/access-release.json').read_text());assert marker['release']==m['release']
K.mkdir();(K/'private').mkdir(mode=0o700);(K/'evidence').mkdir();context=K/'image';context.mkdir()
source=B/'apps/xiaomi-x10/xiaomi_x10_bridge.py';shutil.copyfile(source,context/source.name)
base=m['images']['homecontrol-xiaomi-x10'];tag='hc-x10-startup-base:'+base.removeprefix('sha256:')[:16]
subprocess.run(['docker','image','tag',base,tag],check=True)
(context/'Dockerfile').write_text('FROM '+tag+'\nCOPY xiaomi_x10_bridge.py /app/xiaomi_x10_bridge.py\n')
newtag='hc-x10-online:20261031-r13'
subprocess.run(['docker','build','--pull=false','--network=none','-t',newtag,str(context)],check=True)
image=subprocess.check_output(['docker','image','inspect',newtag,'--format','{{.Id}}'],text=True).strip()
S=K/'source';shutil.copytree(O/'source',S,ignore=shutil.ignore_patterns('__pycache__'))
for p in S.rglob('*'):
 if p.is_file() and p.suffix in ('.py','.sh','.service','.timer','.path','.conf','.json'):
  text=p.read_text()
  if 'hc-f10-20261031-r12' in text:p.write_text(text.replace('hc-f10-20261031-r12',NAME))
# The active old release is r12; all handover/restore adapters point to r13.
for name in ('deploy.py','activate.py','cloud_smoke.py','test_deploy.py'):
 p=S/'scripts/f10_release'/name;text=p.read_text().replace('r12','r13')
 if name=='deploy.py':text=text.replace("OLD='hc-access-20261030-r10'","OLD='hc-f10-20261031-r12'").replace("phase('r10_restored')","phase('previous_release_restored')")
 if name=='test_deploy.py':text=text.replace("expected={'backend','hc_ingest','homecontrol-tuya-poller','homecontrol-gree-climate','homecontrol-xiaomi-x10','homecontrol-ha-growatt-poller','ai-server','frontend'}","expected={'backend','homecontrol-xiaomi-x10'}")
 p.write_text(text)
shutil.copyfile(source,S/'apps/xiaomi-x10'/source.name)
model=json.loads((B/'infra/docker-compose.yml').read_text());changed=['backend','homecontrol-xiaomi-x10']
for name in changed:
 for entry in model['services'][name].get('env_file',[]):entry['path']=entry['path'].replace('/'+m['release']+'/', '/'+NAME+'/')
 for entry in model['services'][name].get('volumes',[]):entry['source']=entry['source'].replace('/'+m['release']+'/', '/'+NAME+'/')
model['services']['homecontrol-xiaomi-x10']['image']=image
(S/'runtime.compose.json').write_text(json.dumps(model,indent=2)+'\n')
rows=json.loads(subprocess.check_output(['docker','inspect',*m['baseline']]))
m.update(release=NAME,previous_release=marker['release'],retry_of=None,hotfix_of=marker['release'],changed_services=changed,
 baseline={r['Name'].lstrip('/'):{'id':r['Id'],'image':r['Image']} for r in rows},
 previous_compose_sha256=hashlib.sha256((B/'infra/docker-compose.yml').read_bytes()).hexdigest(),
 source_sha256={},acceptance_sha256=None,status='hotfix_prepared_not_deployed',ready_for_root_deploy=False,
 scope=['X10 asynchronous startup retained online correction'])
m['images']['homecontrol-xiaomi-x10']=image
images=sorted(set(m['recovery_images'])|{image});archive=K/'private/access-images.tar.gz'
with archive.open('xb') as raw:
 p=subprocess.Popen(['docker','image','save',*images],stdout=subprocess.PIPE)
 with gzip.GzipFile(filename='',mode='wb',compresslevel=1,fileobj=raw,mtime=0) as out:shutil.copyfileobj(p.stdout,out,1024*1024)
 p.stdout.close()
 if p.wait():raise RuntimeError('Offline image export failed')
archive.chmod(0o600)
h=hashlib.sha256()
with archive.open('rb') as f:
 for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
m.update(recovery_images=images,offline_image_archive_sha256=h.hexdigest())
(K/'release.json').write_text(json.dumps(m,indent=2)+'\n')
(K/'evidence/image.json').write_text(json.dumps({'base':base,'image':image,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'dependencies_unchanged':True,'images':len(images),'offline_sha256':h.hexdigest()},indent=2)+'\n')
print(json.dumps({'release':NAME,'image':image,'changed_services':changed,'deployed':False}))
