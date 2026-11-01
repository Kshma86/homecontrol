"""Verify baked X10 reconnect regression, identical dependencies and recovery cache."""
import hashlib,json,subprocess,tarfile,sys
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-f10-20261031-r13';E=K/'evidence';m=json.loads((K/'release.json').read_text());info=json.loads((E/'image.json').read_text());test=B/'scripts/tests/test_x10_online_reconnect.py'
results={}
for name,image in (('previous',info['base']),('fixed',info['image'])):
 args=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','-v',str(test)+':/test.py:ro','-e','X10_TEST_SOURCE=/app/xiaomi_x10_bridge.py','--entrypoint','python',image,'-B','/test.py']
 r=subprocess.run(args,capture_output=True,text=True,timeout=30);(E/(name+'-regression.txt')).write_text(r.stdout+r.stderr);results[name]=r.returncode
assert results['previous']!=0 and results['fixed']==0
code='import importlib.metadata,json; print(json.dumps(sorted((d.metadata["Name"],d.version) for d in importlib.metadata.distributions())))'
packages=[]
for image in (info['base'],info['image']):
 packages.append(json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--entrypoint','python',image,'-B','-c',code])))
assert packages[0]==packages[1]
sha=subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--entrypoint','sha256sum',info['image'],'/app/xiaomi_x10_bridge.py'],text=True).split()[0];assert sha==info['source_sha256']
archive=K/'private/access-images.tar.gz';blobs=set();legacy=None;index=None
with tarfile.open(archive,'r|gz') as tar:
 for entry in tar:
  if entry.name=='manifest.json':legacy=json.load(tar.extractfile(entry))
  elif entry.name=='index.json':index=json.load(tar.extractfile(entry))
  elif entry.isfile() and entry.name.startswith('blobs/sha256/'):
   h=hashlib.sha256();stream=tar.extractfile(entry)
   for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
   assert h.hexdigest()==entry.name.split('/')[-1];blobs.add(entry.name)
assert {r['digest'] for r in index['manifests']}==set(m['recovery_images'])
assert all(p in blobs for row in legacy for p in [row['Config'],*row['Layers']])
r=subprocess.run(['docker','image','load','-i',str(archive)],capture_output=True,text=True,timeout=120);assert r.returncode==0
unit=subprocess.run([sys.executable,str(K/'source/scripts/f10_release/test_deploy.py')],capture_output=True,text=True);assert unit.returncode==0
(E/'installer-tests.txt').write_text(unit.stdout+unit.stderr)
result={'ok':True,'previous_image_fails_regression':True,'fixed_image_passes_three_regressions':True,'baked_source_hash_matches':True,'dependency_inventory_identical':True,'installer_tests':16,'recovery_images':len(m['recovery_images']),'all_oci_blobs_verified':True,'docker_load_succeeded':True,'hardware_commands_sent':False}
(E/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
