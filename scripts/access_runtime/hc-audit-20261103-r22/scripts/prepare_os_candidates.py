#!/usr/bin/env python3
"""Collect signed distro updates, then build exact local image IDs offline.

No service is restarted. Package archives, hashes, complete before/after
inventories and the parent image ID remain available for reproduction.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib,json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
WORK=Path('/tmp/hc23-43-20261102/os-contexts')
OUT=ROOT/'docs/audit-evidence/hc23-43-20261102'
PARENTS={
 'backend':'homecontrol-backend','ingest':'homecontrol-ingest','tuya':'homecontrol-tuya-poller',
 'gree':'homecontrol-gree-climate','x10':'homecontrol-xiaomi-x10','growatt':'homecontrol-ha-growatt-poller',
 'ai-gateway':'homecontrol-ai-server','postgres':'homecontrol-postgres','mqtt':'homecontrol-mqtt',
 'zigbee':'zigbee2mqtt','mdns':'homecontrol-mdns'}
UPSTREAM={'homeassistant':'ghcr.io/home-assistant/home-assistant:2026.10.4',
          'nginx':'nginx:stable-alpine','pgbouncer':'edoburu/pgbouncer:latest'}


def call(args,**kw):return subprocess.run(args,check=True,**kw)


def prepare(name):
 context=WORK/name
 if context.exists():raise ValueError('Never overwrite an existing OS context: '+name)
 context.mkdir(parents=True);(context/'packages').mkdir()
 if name in PARENTS:
  parent=json.loads(subprocess.check_output(['docker','inspect',PARENTS[name]],text=True))[0]['Image']
 else:
  parent=json.loads(subprocess.check_output(['docker','image','inspect',UPSTREAM[name]],text=True))[0]['Id']
 info=json.loads(subprocess.check_output(['docker','image','inspect',parent],text=True))[0]
 tag='hc43-parent-'+name+':20261102'
 call(['docker','tag',parent,tag])
 # /artifacts is the only host write mount, a new directory with public packages.
 # Distro tools validate upstream signed indexes and package hashes on download.
 script=r'''set -eu
mkdir -p /artifacts/packages
if command -v apt-get >/dev/null; then
 echo debian > /artifacts/family
 dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > /artifacts/before.lock
 rm -f /etc/apt/apt.conf.d/docker-clean
 apt-get update
 apt-get -y --no-install-recommends --with-new-pkgs --download-only upgrade
 cp /var/cache/apt/archives/*.deb /artifacts/packages/ 2>/dev/null || true
elif command -v apk >/dev/null; then
 echo alpine > /artifacts/family
 apk info -v | sort > /artifacts/before.lock
 apk update
 # Fetch the installed package names at their current supported-branch version;
 # virtual dependency groups are local metadata and remain in the parent image.
 apk upgrade --simulate | awk '/Upgrading/{print $3}' > /artifacts/names
 if [ -s /artifacts/names ]; then
  apk fetch --recursive --output /artifacts/packages $(cat /artifacts/names)
 fi
else
 echo Unsupported distribution >&2; exit 1
fi
chown -R 1000:1000 /artifacts
'''
 args=['docker','run','--rm','--name','hc43-collect-'+name+'-20261102','--label','hc.audit=hc23-43-20261102',
       '--network','bridge','--user','0:0','--entrypoint','sh','--cap-drop','ALL','--cap-add','CHOWN',
       '--cap-add','DAC_OVERRIDE','--cap-add','FOWNER','--cap-add','SETUID','--cap-add','SETGID',
       '--security-opt','no-new-privileges','--memory','1g','--cpus','1','--pids-limit','128',
       '--mount','type=bind,src='+str(context)+',dst=/artifacts',parent,'-c',script]
 with (context/'download.log').open('w') as log:call(args,stdout=log,stderr=log,timeout=900)
 family=(context/'family').read_text().strip()
 if family=='debian':
  install='DEBIAN_FRONTEND=noninteractive apt-get --no-install-recommends -o Dpkg::Options::=--force-confold -y install /tmp/hc-os-packages/*.deb'
  inventory="dpkg-query -W -f='${binary:Package}\\t${Version}\\n' | sort"
 else:
  install='apk --no-network add --upgrade /tmp/hc-os-packages/*.apk'
  inventory='apk info -v | sort'
 packages=list((context/'packages').glob('*'))
 if not packages:install='true'
 user=info['Config'].get('User') or '0:0'
 recipe=f'''FROM {tag}
USER 0:0
COPY packages/ /tmp/hc-os-packages/
RUN {install} && mkdir -p /opt/hc-release && {inventory} > /opt/hc-release/os-packages.lock && rm -rf /tmp/hc-os-packages
USER {user}
'''
 (context/'Dockerfile').write_text(recipe)
 manifest={'component':name,'parent_image':parent,'parent_repo_digests':info.get('RepoDigests',[]),
           'parent_user':user,'family':family,'networked_phase':'public distro package download only',
           'packages_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in packages},
           'dockerfile_sha256':hashlib.sha256(recipe.encode()).hexdigest(),'candidate_tag':'hc43-'+name+':20261102-candidate'}
 (context/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return manifest


def build(name):
 context=WORK/name;m=json.loads((context/'manifest.json').read_text())
 if any(hashlib.sha256((context/'packages'/p).read_bytes()).hexdigest()!=h for p,h in m['packages_sha256'].items()):
  raise ValueError('Package hash mismatch')
 if hashlib.sha256((context/'Dockerfile').read_bytes()).hexdigest()!=m['dockerfile_sha256']:
  raise ValueError('Dockerfile changed')
 with (context/'build.log').open('w') as log:
  call(['docker','build','--network','none','--pull=false','-t',m['candidate_tag'],str(context)],stdout=log,stderr=log,timeout=900)
 image=json.loads(subprocess.check_output(['docker','image','inspect',m['candidate_tag']],text=True))[0]
 m['image']=image['Id']
 code=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
       '--user','1000:1000','--entrypoint','cat',m['image'],'/opt/hc-release/os-packages.lock']
 lock=subprocess.check_output(code,text=True);(context/'after.lock').write_text(lock)
 m['before_lock_sha256']=hashlib.sha256((context/'before.lock').read_bytes()).hexdigest()
 m['after_lock_sha256']=hashlib.sha256(lock.encode()).hexdigest()
 (context/'built.json').write_text(json.dumps(m,indent=2)+'\n');return m


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','build'))
 p.add_argument('--components',nargs='+',choices=tuple(PARENTS)+tuple(UPSTREAM),required=True);a=p.parse_args()
 results={}
 for name in a.components:
  try:
   m=prepare(name) if a.action=='prepare' else build(name);results[name]={'ok':True,**m}
   print(name,'ok',flush=True)
  except Exception as error:
   results[name]={'ok':False,'error_type':type(error).__name__};print(name,type(error).__name__,flush=True)
  (OUT/('os-'+a.action+'.json')).write_text(json.dumps(results,indent=2)+'\n')
 return 0 if all(r['ok'] for r in results.values()) else 1


if __name__=='__main__':raise SystemExit(main())
