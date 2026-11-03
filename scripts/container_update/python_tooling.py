#!/usr/bin/env python3
"""Upgrade authenticated pip wheel offline; keep every application dependency."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path('/srv/docker/homecontrol/maintenance/container-update-20261103')
COMPONENTS=('homecontrol-backend','homecontrol-ingest','homecontrol-tuya-poller','homecontrol-gree-climate',
            'homecontrol-xiaomi-x10','homecontrol-ha-growatt-poller','homecontrol-ai-server','homecontrol-mdns')
CODE='''import importlib.metadata as m,json,sys,re
def canonicalize_name(name):return re.sub(r'[-_.]+','-',name).lower()
rows={}
for d in m.distributions():
 name=canonicalize_name(d.metadata['Name'])
 if name in rows and rows[name]!=d.version:raise ValueError('Conflicting installed distributions')
 rows[name]=d.version
print(json.dumps({'python':list(sys.version_info[:3]),'packages':rows},sort_keys=True))
'''


def call(args,**kw):return subprocess.run(args,check=True,timeout=600,capture_output=True,text=True,**kw)


def inventory(image):
    return json.loads(call(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--entrypoint','python',image,'-B','-c',CODE]).stdout)


def build(item):
    name,parent=item
    work=ROOT/'python-tooling-builds'/name
    if (work/'built.json').is_file():
        result=json.loads((work/'built.json').read_text())
        if result['parent_image']!=parent or not result['ok']:raise ValueError('Invalid previous build')
        current=inventory(result['image'])
        if current!=json.loads((work/'after-python.json').read_text()):raise ValueError('Previous build changed')
        return result
    if work.exists():
        # Only the authenticated wheel and lock may exist after an inventory failure.
        if set(p.name for p in work.iterdir())-{'pip-26.3-py3-none-any.whl','python-tooling.lock'}:
            raise ValueError('Unreviewed partial build')
    else:work.mkdir(mode=0o700,parents=True)
    metadata=json.loads((ROOT/'python-tooling/wheel-manifest.json').read_text());wheel=ROOT/'python-tooling'/metadata['filename']
    if hashlib.sha256(wheel.read_bytes()).hexdigest()!=metadata['sha256']:raise ValueError('pip wheel changed')
    shutil.copyfile(wheel,work/wheel.name)
    (work/'python-tooling.lock').write_text('pip=='+metadata['version']+' --hash=sha256:'+metadata['sha256']+'\n')
    before=inventory(parent)
    if tuple(before['python'][:2])<(3,10):raise ValueError('Unsupported Python for pip 26.3')
    (work/'before-python.json').write_text(json.dumps(before,indent=2)+'\n')
    tag='hc-container-pip-'+name+':20261103';base_tag='hc-container-pip-'+name+'-parent:20261103'
    if subprocess.run(['docker','image','inspect',tag],capture_output=True).returncode==0:raise ValueError('New candidate tag required')
    existing=subprocess.run(['docker','image','inspect',base_tag],capture_output=True,text=True)
    if existing.returncode==0 and json.loads(existing.stdout)[0]['Id']!=parent:raise ValueError('Parent tag changed')
    call(['docker','tag',parent,base_tag])
    config=json.loads(call(['docker','image','inspect',parent]).stdout)[0]['Config'];user=config.get('User') or '0:0'
    recipe=f'''FROM {base_tag}
USER 0:0
COPY {wheel.name} python-tooling.lock /tmp/hc-python-update/
RUN python -m pip install --disable-pip-version-check --no-index --no-deps --no-cache-dir --upgrade --require-hashes --find-links=/tmp/hc-python-update -r /tmp/hc-python-update/python-tooling.lock && python -m pip check && rm -rf /tmp/hc-python-update
USER {user}
'''
    (work/'Dockerfile').write_text(recipe)
    with (work/'build.log').open('w') as stream:
        subprocess.run(['docker','build','--network','none','--pull=false','-t',tag,str(work)],stdout=stream,stderr=stream,check=True,timeout=900)
    info=json.loads(call(['docker','image','inspect',tag]).stdout)[0];after=inventory(info['Id'])
    if after['python']!=before['python'] or after['packages'].get('pip')!=metadata['version']:raise ValueError('Unexpected Python/pip version')
    delta={n:(before['packages'].get(n),after['packages'].get(n)) for n in set(before['packages'])|set(after['packages']) if before['packages'].get(n)!=after['packages'].get(n)}
    if set(delta)!={'pip'}:raise ValueError('Application Python dependencies changed')
    for field in ('Entrypoint','Cmd','Env','WorkingDir','ExposedPorts','Volumes','Healthcheck'):
        if info['Config'].get(field)!=config.get(field):raise ValueError('Image startup configuration changed')
    (work/'after-python.json').write_text(json.dumps(after,indent=2)+'\n')
    result={'ok':True,'component':name,'parent_image':parent,'image':info['Id'],'tag':tag,
            'pip_from':before['packages']['pip'],'pip_to':metadata['version'],'other_python_packages_unchanged':True,
            'wheel_sha256':metadata['sha256'],'build_network':'none','pip_check':'passed','deployment_performed':False}
    (work/'built.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    lock=json.loads((ROOT/'candidate-image-lock.json').read_text());rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(build,(n,lock[n])) for n in COMPONENTS]):
            row=future.result();rows.append(row)
            (ROOT/'python-tooling-candidates.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(json.dumps({'component':row['component'],'pip_from':row['pip_from'],'pip_to':row['pip_to'],'image':row['image']}),flush=True)
    for row in rows:lock[row['component']]=row['image']
    (ROOT/'candidate-image-lock-final.json').write_text(json.dumps(lock,indent=2)+'\n')


if __name__=='__main__':main()
