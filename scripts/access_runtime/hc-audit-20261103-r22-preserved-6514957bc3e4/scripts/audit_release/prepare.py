"""Build an app-only audit completion release; never change production services."""
import argparse,ast,copy,gzip,hashlib,json,os,re,shutil,subprocess,sys,tarfile
from pathlib import Path
BASE=Path('/srv/docker/homecontrol');OLD='hc-security-20261102-r18';NAME='hc-audit-20261103-r22'
KIT=BASE/'backups/releases'/NAME
EVIDENCE=BASE/'docs/audit-evidence/audit-final-r19-20261102'
COMPONENTS={'backend':('infra/backend','homecontrol-backend'),
 'mdns':('infra/mdns','homecontrol-mdns'),
 'homecontrol-ha-growatt-poller':('apps/ha-growatt-poller','homecontrol-ha-growatt-poller')}
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as stream:
  for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def image(c):return subprocess.check_output(['docker','inspect','-f','{{.Image}}',c],text=True).strip()
def source():
 assert not KIT.exists(),'Never overwrite a release'
 assert read(BASE/'infra/access-release.json')['release']==OLD
 prior=BASE/'backups/releases'/OLD;original=read(prior/'release.json')
 assert all(digest(prior/'source'/n)==h for n,h in original['source_sha256'].items())
 KIT.mkdir();(KIT/'private').mkdir(mode=0o700);(KIT/'evidence').mkdir();(KIT/'tools').mkdir()
 target=KIT/'source';shutil.copytree(prior/'source',target,ignore=shutil.ignore_patterns('__pycache__'))
 reviewed=read(EVIDENCE/'reviewed-inputs.json');changes=[]
 for name,expected in reviewed.items():
  if name.startswith(('docs/','apps/ai-node/')) or name in ('AUDIT_REPAIR.md','DEPLOYMENT_PREP.md'):continue
  dest=target/name;live=BASE/name
  if expected is None:
   assert not live.exists();dest.unlink(missing_ok=True)
  else:
   assert digest(live)==expected,name
   dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(live,dest)
  changes.append(name)
 for name in reviewed:
  if name.startswith(('docs/','apps/ai-node/')) or name in ('AUDIT_REPAIR.md','DEPLOYMENT_PREP.md'):
   p=BASE/name
   if p.is_file():
    dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 shutil.copyfile(BASE/'infra/backend/tests/test_health_routes.py',target/'infra/backend/tests/test_health_routes.py')
 # Shared fixtures are public test support, not additional service changes.
 for folder in ('apps/bridge_runtime/tests','apps/xiaomi-x10/tests'):
  shutil.copytree(BASE/folder,target/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
 for p in (BASE/'apps/hc_ingest').glob('test_*.py'):shutil.copyfile(p,target/'apps/hc_ingest'/p.name)
 for name in ('command_dispatcher.py','worker_health.py'):
  src=BASE/'apps/bridge_runtime'/name
  assert any(digest(p)==digest(src) for p in target.rglob(name))
  dest=target/'apps/bridge_runtime'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
 shutil.copytree(BASE/'scripts/audit_release',target/'scripts/audit_release',ignore=shutil.ignore_patterns('__pycache__'))
 for p in target.rglob('*'):
  if p.is_file() and p.suffix in ('.py','.sh','.service','.timer','.path','.conf','.json'):
   text=p.read_text()
   if OLD in text:p.write_text(text.replace(OLD,NAME))
 core=target/'scripts/f10_release/deploy.py';text=core.read_text()
 text,n=re.subn(r'^OLD=.+$', 'OLD='+repr(OLD),text,flags=re.M);assert n==1;core.write_text(text)
 # The builder retains its explicit prior baseline and is not a runtime entrypoint.
 shutil.copyfile(BASE/'scripts/audit_release/prepare.py',target/'scripts/audit_release/prepare.py')
 router=target/'scripts/router_release/activate.py';text=router.read_text().replace('router-r18','router-r19').replace("say('r18:","say('r19:")
 text=text.replace('ellenőrzött platform és host mentő átállítása','backend, mDNS, Growatt és host mentő átállítása');router.write_text(text)
 export=target/'scripts/router_release/prepare_audit_restore.py';text=export.read_text().replace('/tmp/hc-security-audit-20261102/input','/tmp/hc-audit-final-r19-20261102/input').replace('docs/audit-evidence/hc23-43-20261102/live-restore-input','docs/audit-evidence/audit-final-r19-20261102/live-restore-input');export.write_text(text)
 model=read(BASE/'infra/docker-compose.yml')
 for service in COMPONENTS:
  for row in model['services'][service].get('env_file',[]):row['path']=row['path'].replace('/'+OLD+'/','/'+NAME+'/')
  for row in model['services'][service].get('volumes',[]):row['source']=row['source'].replace('/'+OLD+'/','/'+NAME+'/')
 write(target/'runtime.compose.json',model)
 names=list(original['baseline'])
 raw=subprocess.check_output(['docker','inspect','--format','{"name":{{json .Name}},"id":{{json .Id}},"image":{{json .Image}}}',*names],text=True)
 baseline={x['name'].lstrip('/'):{'id':x['id'],'image':x['image']} for x in map(json.loads,raw.splitlines())}
 m=copy.deepcopy(original);m.update(release=NAME,previous_release=OLD,prepared=True,deployed=False,ready_for_root_deploy=False,
  changed_services=list(COMPONENTS),baseline=baseline,previous_compose_sha256=digest(BASE/'infra/docker-compose.yml'),
  images={s:baseline[c]['image'] for s,(_,c) in COMPONENTS.items()},source_sha256={},acceptance_sha256=None,
  scope=['HC-15','HC-16','HC-20','HC-23','HC-24','HC-26'],
  unchanged=[n for n in names if n not in {c for _,c in COMPONENTS.values()}],
  status='preparing_audit_completion_not_deployed',recovery_images=[],
  full_vm_candidate_restore_verified=False,prior_recovery_proof='docs/audit-evidence/hc23-43-closure-20261102/bounded-lab/vm-acceptance.json',
  pending_root_steps=['private copy and encrypted secret roundtrip','verified pre-cutover backup','three component cutover and IPC/health checks','fresh HC/Git/router backup and isolated PostgreSQL restore'])
 write(KIT/'release.json',m)
 shutil.copyfile(prior/'tools/rclone',KIT/'tools/rclone');(KIT/'tools/rclone').chmod(0o755)
 write(KIT/'evidence/source-overlay.json',{'ok':True,'reviewed_source_deltas':changes,'test_policy':'mandatory deployed policy; no standard-policy mutation in release','no_production_change':True})
 # Transaction test scope follows the actual three-component handover.
 tests=target/'scripts/f10_release/test_deploy.py';text=tests.read_text();text,n=re.subn(r'^  expected=.+$', '  expected='+repr(set(COMPONENTS)),text,flags=re.M);assert n==1;tests.write_text(text)
 print(json.dumps({'release':NAME,'source_delta_count':len(changes),'production_changed':False}))
def build():
 m=read(KIT/'release.json');model=read(KIT/'source/runtime.compose.json');inputs=KIT/'build-inputs';inputs.mkdir()
 receipt={}
 for service,(folder,container) in COMPONENTS.items():
  base=m['baseline'][container]['image'];name={'backend':'backend','mdns':'mdns','homecontrol-ha-growatt-poller':'growatt'}[service]
  root=inputs/name;root.mkdir();(root/'source').mkdir();source=KIT/'source'/folder
  files=sorted(source.glob('*.py')) if service=='backend' else [source/('mdns_responder.py' if service=='mdns' else 'ha_growatt_poller.py')]
  for f in files:shutil.copyfile(f,root/'source'/f.name)
  tag='hc-audit-base-'+name+':20261102-r19';subprocess.run(['docker','tag',base,tag],check=True)
  assert subprocess.check_output(['docker','image','inspect',tag,'-f','{{.Id}}'],text=True).strip()==base
  recipe='FROM '+tag+'\n'
  if service=='backend':recipe+='USER 0:0\nRUN rm -f /app/*.py\n'
  recipe+='COPY source/*.py /app/\n'
  if service=='backend':recipe+='USER 10001:10001\n'
  recipe+='LABEL org.homecontrol.release="'+NAME+'" org.homecontrol.base-image="'+base+'"\n'
  (root/'Dockerfile').write_text(recipe)
  env=dict(os.environ,DOCKER_BUILDKIT='0');candidate='hc-audit-'+name+':20261102-r19'
  with (KIT/'evidence'/('build-'+name+'.log')).open('w') as log:
   subprocess.run(['docker','build','--network','none','--pull=false','--no-cache','-t',candidate,str(root)],check=True,stdout=log,stderr=subprocess.STDOUT,env=env)
  selected=json.loads(subprocess.check_output(['docker','image','inspect',candidate],text=True))[0]
  old=json.loads(subprocess.check_output(['docker','image','inspect',base],text=True))[0]
  assert selected['RootFS']['Layers'][:len(old['RootFS']['Layers'])]==old['RootFS']['Layers']
  for field in ('Env','Entrypoint','Cmd','User','Healthcheck','WorkingDir'):
   assert selected['Config'].get(field)==old['Config'].get(field),(service,field)
  m['images'][service]=selected['Id'];model['services'][service]['image']=selected['Id']
  receipt[name]={'base_image':base,'base_tag':tag,'image':selected['Id'],'dependency_install_commands':0,'runtime_contract_preserved':True,
   'source_sha256':{p.name:digest(p) for p in (root/'source').glob('*.py')}}
 write(KIT/'source/runtime.compose.json',model);write(KIT/'evidence/image-builds.json',receipt)
 # Current platform plus the three previous images is sufficient for full restore
 # and exact r18 rollback. Old unrelated candidate/test images are not bundled.
 m['recovery_images']=sorted({v['image'] for v in m['baseline'].values()}|set(m['images'].values()))
 write(KIT/'release.json',m)
 write(KIT/'evidence/candidate-image-lock.json',{c:m['images'][s] for s,(_,c) in COMPONENTS.items()})
 write(KIT/'evidence/build-inputs.json',{'sha256':{str(p.relative_to(inputs)):digest(p) for p in inputs.rglob('*') if p.is_file()}})
 print(json.dumps({'built':len(receipt),'recovery_images':len(m['recovery_images']),'production_changed':False}))
def archive():
 m=read(KIT/'release.json');p=KIT/'private/access-images.tar.gz';assert not p.exists()
 with p.open('xb') as raw:
  proc=subprocess.Popen(['docker','image','save',*m['recovery_images']],stdout=subprocess.PIPE)
  with gzip.GzipFile(filename='',mode='wb',compresslevel=1,fileobj=raw,mtime=0) as zipped:shutil.copyfileobj(proc.stdout,zipped,1024**2)
  proc.stdout.close();assert proc.wait()==0;raw.flush();os.fsync(raw.fileno())
 p.chmod(0o600);m['offline_image_archive_sha256']=digest(p);m['rclone_sha256']=digest(KIT/'tools/rclone');write(KIT/'release.json',m)
 with (KIT/'evidence/offline-load.log').open('w') as log:subprocess.run(['docker','image','load','-i',str(p)],check=True,stdout=log,stderr=subprocess.STDOUT)
 for item in m['recovery_images']:assert subprocess.check_output(['docker','image','inspect',item,'-f','{{.Id}}'],text=True).strip()==item
 write(KIT/'evidence/offline-load.json',{'ok':True,'archive_sha256':m['offline_image_archive_sha256'],'verified_images':m['recovery_images'],'size_bytes':p.stat().st_size})
 print(json.dumps({'offline_load_verified':True,'images':len(m['recovery_images']),'size_bytes':p.stat().st_size}))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('source','build','archive'));a=p.parse_args();globals()[a.action]()
