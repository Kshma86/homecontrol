import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path('/srv/docker/homecontrol')
OUT = ROOT / 'docs/audit-evidence/hc32-23-43-20261031'
def run(args):
    return subprocess.check_output(args, text=True, timeout=60)
items = json.loads(run(['docker', 'inspect', *run(['docker','ps','-aq']).split()]))
containers = {x['Name'].lstrip('/'): {k:v for k,v in {
    'id':x['Id'], 'image':x['Image'], 'started_at':x['State']['StartedAt'],
    'restart_count':x['RestartCount'], 'status':x['State']['Status']}.items()} for x in items}
code = "import importlib.metadata,json; print(json.dumps(sorted({(d.metadata['Name'],d.version) for d in importlib.metadata.distributions()})))"
names = ['homecontrol-'+n for n in ('backend','ingest','tuya-poller','gree-climate','xiaomi-x10','ai-server','ha-growatt-poller')] + ['homeassistant']
def packages(name):
    return name, json.loads(run(['docker','exec',name,'python','-B','-c',code]))
inventories = dict(concurrent.futures.ThreadPoolExecutor(4).map(packages, names))
images={}
for image in sorted({x['image'] for x in containers.values()}):
    info=json.loads(run(['docker','image','inspect',image]))[0]
    images[image]={k:info.get(k) for k in ('Id','RepoDigests','Architecture','Os','Created')}
paths = [ROOT/'HC_REFACTOR_AUDIT.md', ROOT/'infra/docker-compose.yml']
for folder in ['infra/backend','infra/frontend','apps/bridge_runtime','apps/tuya-poller','apps/gree-climate','apps/xiaomi-x10','apps/ha-growatt-poller','apps/hc_ingest']:
    base=ROOT/folder
    paths += [p for p in base.glob('*') if p.is_file() and (p.suffix=='.py' or p.name in ('Dockerfile','requirements.txt','package.json','package-lock.json'))]
source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
for p in paths:
    dest=OUT/'original'/p.relative_to(ROOT)
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():dest.write_bytes(p.read_bytes())
result={'at':datetime.now(timezone.utc).isoformat(),'containers':containers,'images':images,'python':inventories,'source_sha256':source}
target=OUT/'before.json'
if target.exists():raise SystemExit('baseline already exists')
target.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'containers':len(containers),'python_packages':{k:len(v) for k,v in inventories.items()},'source_files':len(source)}))
