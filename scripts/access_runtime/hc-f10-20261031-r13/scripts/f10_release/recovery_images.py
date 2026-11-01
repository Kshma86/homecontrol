"""Build an offline union of new and previous immutable application/platform images."""
import gzip,hashlib,json,os,subprocess,tarfile
from pathlib import Path
K=Path('/srv/docker/homecontrol/backups/releases/hc-f10-20261031-r13')
m=json.loads((K/'release.json').read_text())
images=sorted(set(m['images'].values())|{r['image'] for r in m['baseline'].values()})
target=K/'private/access-images.tar.gz'
if target.exists():raise SystemExit('Archive exists; reconcile instead of overwrite')
tmp=target.with_suffix('.partial')
if not tmp.exists():
 with tmp.open('xb') as raw:
  p=subprocess.Popen(['docker','image','save',*images],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  with gzip.GzipFile(filename='',mode='wb',compresslevel=1,fileobj=raw,mtime=0) as out:
   while chunk:=p.stdout.read(1024*1024):out.write(chunk)
  p.stdout.close();errors=p.stderr.read();rc=p.wait()
  if rc:raise RuntimeError('Docker image export failed')
  raw.flush();os.fsync(raw.fileno())
with tarfile.open(tmp,'r|gz') as tar:
 exported=None;index=None;blobs=set()
 for entry in tar:
  if entry.name=='manifest.json':exported=json.load(tar.extractfile(entry))
  elif entry.name=='index.json':index=json.load(tar.extractfile(entry))
  elif entry.isfile() and entry.name.startswith('blobs/sha256/'):
   h=hashlib.sha256();stream=tar.extractfile(entry)
   for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
   if h.hexdigest()!=entry.name.split('/')[-1]:raise RuntimeError('Corrupt OCI blob')
   blobs.add(entry.name)
 if not exported:raise RuntimeError('Missing Docker export manifest')
 # Docker uses OCI digest paths in recent versions; legacy exports use <id>.json.
 actual={row['digest'] for row in index['manifests']} if index else {'sha256:'+row['Config'].split('/')[-1].removesuffix('.json') for row in exported}
 if actual!=set(images):raise RuntimeError('Offline image set mismatch')
 if index and any(path not in blobs for row in exported for path in [row['Config'],*row['Layers']]):
  raise RuntimeError('Missing current-platform config/layer blob')
os.replace(tmp,target);target.chmod(0o600)
h=hashlib.sha256()
with target.open('rb') as f:
 for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
m.update(recovery_images=images,offline_image_archive_sha256=h.hexdigest())
(K/'release.json').write_text(json.dumps(m,indent=2)+'\n')
r={'ok':True,'images':len(images),'size_bytes':target.stat().st_size,'sha256':h.hexdigest(),'previous_images_included':True}
(K/'evidence/recovery-images.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
