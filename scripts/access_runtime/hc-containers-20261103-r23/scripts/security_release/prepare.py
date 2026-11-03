#!/usr/bin/env python3
"""Freeze the tested r18 platform/security candidate over the sealed active r16."""
import argparse,gzip,hashlib,json,os
from pathlib import Path
import shutil,subprocess,tarfile

BASE=Path('/srv/docker/homecontrol');OLD='hc-router-backup-20261101-r16';NAME='hc-containers-20261103-r23'
KIT=BASE/'backups/releases'/NAME
EVIDENCE=BASE/'docs/audit-evidence/hc23-43-20261102'
MAPPING={'ai-server':'ai-gateway','backend':'backend','frontend':'frontend','hc_ingest':'ingest',
 'homecontrol-gree-climate':'gree','homecontrol-ha-growatt-poller':'growatt','homecontrol-tuya-poller':'tuya',
 'homecontrol-xiaomi-x10':'x10','mdns':'mdns','mqtt':'mqtt','pgbouncer':'pgbouncer','postgres':'postgres','proxy':'nginx','zigbee2mqtt':'zigbee'}
FILES=('scripts/backup_archive_worker.sh','scripts/backup_ha_sqlite.py','scripts/hc_ha_upgrade_probe.py',
 'scripts/check_hc_tests.py','scripts/stage_hc_test_source.py','scripts/hc_test_suite.py','scripts/dependency_audit.py',
 'scripts/prepare_os_candidates.py','scripts/access_release/restore_assets.py',
 'infra/backend/tests/__init__.py','infra/backend/tests/test_backup_runner.py','infra/backend/tests/test_dependency_audit.py',
 'infra/backend/tests/test_access_release.py',
 'infra/mdns/Dockerfile')


def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
 return h.hexdigest()


def patch(path,before,after):
 text=path.read_text()
 if text.count(before)!=1:raise ValueError('Unexpected source context: '+before[:75])
 path.write_text(text.replace(before,after))


def source():
 if KIT.exists():raise ValueError('Never overwrite a release directory')
 if json.loads((BASE/'infra/access-release.json').read_text())['release']!=OLD:raise ValueError('Baseline changed')
 prior=BASE/'backups/releases'/OLD;m=json.loads((prior/'release.json').read_text())
 if any(digest(prior/'source'/n)!=h for n,h in m['source_sha256'].items()):raise ValueError('Sealed r16 changed')
 candidates=json.loads((EVIDENCE/'os-candidates.json').read_text())['components']
 images={n:row['image'] for n,row in candidates.items()}
 images['frontend']=subprocess.check_output(['docker','image','inspect','hc43-frontend:20261102-candidate','--format','{{.Id}}'],text=True).strip()
 KIT.mkdir();(KIT/'private').mkdir(mode=0o700);(KIT/'evidence').mkdir();(KIT/'tools').mkdir()
 target=KIT/'source';shutil.copytree(prior/'source',target,ignore=shutil.ignore_patterns('__pycache__'))
 for name in FILES:
  p=target/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,p)
 for folder in ('scripts/security_release','scripts/tests'):
  shutil.copytree(BASE/folder,target/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copytree(BASE/'infra/frontend',target/'infra/frontend',dirs_exist_ok=True,
                 ignore=shutil.ignore_patterns('node_modules','dist','__pycache__','.env*','.npm-cache'))
 shutil.copyfile(BASE/'hc-v31-qspi-handoff-20261009-rcp1-foundation.zip',target/'hc-v31-qspi-handoff-20261009-rcp1-foundation.zip')
 for path in target.rglob('*'):
  if path.is_file() and path.suffix in ('.py','.sh','.service','.timer','.path','.conf','.json'):
   text=path.read_text()
   if OLD in text:path.write_text(text.replace(OLD,NAME))
 # The builder describes the previous baseline; unlike runtime entrypoints its
 # OLD constant must not be rewritten to the new release name.
 shutil.copyfile(BASE/'scripts/security_release/prepare.py',target/'scripts/security_release/prepare.py')
 deploy=target/'scripts/f10_release/deploy.py'
 patch(deploy,"OLD='hc-router-backup-20261101-r15'",'OLD='+repr(OLD))
 patch(deploy,"def container(service):\n", "def container(service):\n    if service=='zigbee2mqtt':return 'zigbee2mqtt'\n")
 patch(deploy,"if not previous and row['State'].get('Health',{}).get('Status')!='healthy':raise ValueError('Application health pending')",
       "if not previous and service in m['health_required'] and row['State'].get('Health',{}).get('Status')!='healthy':raise ValueError('Application health pending')")
 patch(deploy,"                if name in changed:continue","                if name in changed or name=='homeassistant':continue")
 activation=target/'scripts/router_release/activate.py';text=activation.read_text().replace('router-r16','router-r18').replace("say('r16:","say('r18:")
 text=text.replace('backend/frontend és host mentő átállítása','ellenőrzött platform és host mentő átállítása');activation.write_text(text)
 export=target/'scripts/router_release/prepare_audit_restore.py';text=export.read_text().replace('/tmp/hc-router-audit-20261101/input','/tmp/hc-security-audit-20261102/input').replace('docs/audit-evidence/ai-ssd-closure-20261101','docs/audit-evidence/hc23-43-20261102/live-restore-input');export.write_text(text)
 model=json.loads((BASE/'infra/docker-compose.yml').read_text())
 health=[]
 for service,component in MAPPING.items():
  item=model['services'][service];item['image']=images[component];item['pull_policy']='never'
  for row in item.get('env_file',[]):row['path']=row['path'].replace('/'+OLD+'/','/'+NAME+'/')
  for row in item.get('volumes',[]):row['source']=row['source'].replace('/'+OLD+'/','/'+NAME+'/')
  info=json.loads(subprocess.check_output(['docker','image','inspect',images[component]],text=True))[0]
  check=item.get('healthcheck') or info['Config'].get('Healthcheck',{})
  if not check.get('disable') and check.get('test',check.get('Test')) not in (None,[],['NONE']):health.append(service)
 (target/'runtime.compose.json').write_text(json.dumps(model,indent=2)+'\n')
 ha_path=BASE/'homeassistant/docker-compose.yml'
 ha=json.loads(subprocess.check_output(['docker','compose','-f',str(ha_path),'config','--format','json'],text=True))
 ha['services']['homeassistant']['image']=images['homeassistant'];ha['services']['homeassistant']['pull_policy']='never'
 (target/'homeassistant').mkdir(exist_ok=True)
 (target/'homeassistant/docker-compose.yml').write_text(json.dumps(ha,indent=2)+'\n')
 rows=json.loads(subprocess.check_output(['docker','inspect',*m['baseline']],text=True))
 ha_row=next(row for row in rows if row['Name']=='/homeassistant')
 m.update(release=NAME,previous_release=OLD,prepared=True,deployed=False,ready_for_root_deploy=False,
  previous_compose_sha256=digest(BASE/'infra/docker-compose.yml'),
  previous_ha_compose_sha256=digest(ha_path),previous_ha_configuration_sha256=digest(BASE/'homeassistant/config/configuration.yaml'),
  homeassistant_image=images['homeassistant'],homeassistant_project=ha_row['Config']['Labels']['com.docker.compose.project'],
  images={service:images[component] for service,component in MAPPING.items()},health_required=health,
  changed_services=list(MAPPING),source_sha256={},acceptance_sha256=None,
  baseline={r['Name'].lstrip('/'):{'id':r['Id'],'image':r['Image']} for r in rows},
  scope=['HC-23 active platform reproducibility/test profiles','HC-43 maintained HA, OS updates and Vite patch'],
  status='preparing_security_platform_not_deployed')
 # Keep the previous recovery set and add every new image, including separate HA.
 m['recovery_images']=sorted(set(m['recovery_images'])|set(images.values()))
 (KIT/'release.json').write_text(json.dumps(m,indent=2)+'\n')
 shutil.copyfile(prior/'tools/rclone',KIT/'tools/rclone');(KIT/'tools/rclone').chmod(0o755)
 tests=target/'scripts/f10_release/test_deploy.py'
 text=tests.read_text();old="expected={'backend','frontend'}"
 if old not in text:raise ValueError('Expected r16 scope assertion')
 tests.write_text(text.replace(old,'expected='+repr(set(MAPPING))))
 print(json.dumps({'release':NAME,'changed_services':len(MAPPING),'separate_homeassistant':True,'ready':False}))


def archive():
 m=json.loads((KIT/'release.json').read_text());dest=KIT/'private/access-images.tar.gz'
 if dest.exists():raise ValueError('Offline archive already exists')
 with dest.open('xb') as raw:
  p=subprocess.Popen(['docker','image','save',*m['recovery_images']],stdout=subprocess.PIPE)
  with gzip.GzipFile(filename='',mode='wb',compresslevel=1,fileobj=raw,mtime=0) as compressed:
   shutil.copyfileobj(p.stdout,compressed,1024*1024)
  p.stdout.close()
  if p.wait():raise RuntimeError('Image save failed')
  raw.flush();os.fsync(raw.fileno())
 dest.chmod(0o600)
 with tarfile.open(dest,'r|gz') as stream:
  actual=None;blobs=set();exported=None
  for entry in stream:
   if entry.name=='index.json':actual={row['digest'] for row in json.load(stream.extractfile(entry))['manifests']}
   elif entry.name=='manifest.json':exported=json.load(stream.extractfile(entry))
   elif entry.isfile() and entry.name.startswith('blobs/sha256/'):
    h=hashlib.sha256()
    data=stream.extractfile(entry)
    for chunk in iter(lambda:data.read(1024*1024),b''):h.update(chunk)
    if h.hexdigest()!=entry.name.rsplit('/',1)[1]:raise ValueError('OCI blob hash mismatch')
    blobs.add(entry.name)
  if actual!=set(m['recovery_images']):raise ValueError('Offline image inventory mismatch')
  if not exported or any(path not in blobs for row in exported for path in (row['Config'],*row['Layers'])):
   raise ValueError('Missing offline image layer')
 m['offline_image_archive_sha256']=digest(dest);m['rclone_sha256']=digest(KIT/'tools/rclone')
 (KIT/'release.json').write_text(json.dumps(m,indent=2)+'\n')
 (KIT/'evidence/recovery-images.json').write_text(json.dumps({'ok':True,'images':len(m['recovery_images']),'sha256':m['offline_image_archive_sha256'],'size_bytes':dest.stat().st_size},indent=2)+'\n')
 print('Offline image archive verified')


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('source','archive'));a=p.parse_args()
 {'source':source,'archive':archive}[a.action]()
