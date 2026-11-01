from pathlib import Path
import json,subprocess,io,tarfile,hashlib,runpy,contextlib
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-f10-20261031-r13';W=Path('/tmp/hc-access-combined-20261031')
with contextlib.redirect_stdout(io.StringIO()):v=runpy.run_path('/tmp/hc-access-r10-20261030/check_images.py')
objects=v['objects'];seen=v['seen'];docker=v['docker_manifest'];info=v['info']
def complete(digest):
 node=objects.get(digest)
 if not isinstance(node,dict):return False
 if node.get('architecture')=='amd64' and node.get('os')=='linux':
  return any('sha256:'+r['Config'].rsplit('/',1)[-1]==digest for r in docker)
 if 'config' in node:
  config=objects.get(node['config']['digest'],{})
  return config.get('architecture')=='amd64' and config.get('os')=='linux' and node['config']['digest'] in seen and all(x['digest'] in seen for x in node.get('layers',[]))
 return any(complete(x['digest']) for x in node.get('manifests',[]) if not x.get('platform') or x['platform'].get('architecture')=='amd64' and x['platform'].get('os')=='linux')
assert all(complete(identity) for identity in info['images'])
archive=K/'private/runtime/images/access-images.tar.gz'
r=subprocess.run(['age','-d','-i',str(B/'infra/ssh/homecontrol-secrets-age-key.txt'),str(K/'private/homecontrol-secrets-access.tar.gz.age')],capture_output=True,check=True)
with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:gz') as t:
 policies=[m for m in t if m.name.lstrip('./')=='srv/docker/homecontrol/infra/ssh/hc-f10-20261031-r13/network-policy.json']
 assert len(policies)==1
 policy=json.load(t.extractfile(policies[0]));assert policy['esp_confirmed'] is True and policy['esp_ip']=='192.168.1.179'
result={'ok':True,'offline_image_count':len(info['images']),'all_blob_sha256_verified':True,'blob_count':len(seen),'linux_amd64_complete_for_all_requested_images':True,'upstream_other_platform_or_attestation_descriptors_omitted':len(v['missing']),'image_archive_bytes':archive.stat().st_size,'image_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'actual_age_decryption_verified':True,'encrypted_bundle_esp_confirmed':True,'esp_ip':'192.168.1.179','production_bundle_installed':False}
(W/'evidence/recovery-assets.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
