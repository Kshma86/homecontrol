#!/usr/bin/env python3
"""Build only the reviewed OS deltas, with authenticated public package inputs."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import sys

sys.dont_write_bytecode=True
BASE=Path('/srv/docker/homecontrol')
ROOT=BASE/'maintenance/container-update-20261103'
spec=importlib.util.spec_from_file_location('container_probe',Path(__file__).with_name('probe.py'))
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


COLLECT=r'''set -eu
mkdir -p /artifacts/packages
if command -v apt-get >/dev/null; then
 dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > /artifacts/before.lock
 rm -f /etc/apt/apt.conf.d/docker-clean
 apt-get -o APT::Update::Error-Mode=any update
 apt-get --simulate --no-remove --with-new-pkgs upgrade > /artifacts/transactions.txt
 apt-get --download-only --no-remove --no-install-recommends -y install "$@"
 for spec in "$@"; do apt-cache show "$spec" >> /artifacts/packages.metadata; done
 cp /var/cache/apt/archives/*.deb /artifacts/packages/
 mkdir /artifacts/signed-indexes
 cp /var/lib/apt/lists/*InRelease /artifacts/signed-indexes/
else
 apk info -v | sort > /artifacts/before.lock
 apk update
 apk upgrade --simulate > /artifacts/transactions.txt
 apk fetch --recursive --output /artifacts/packages "$@"
fi
chown -R 1000:1000 /artifacts
'''


def inventory_difference(family,before,after):
    if family=='debian':
        def parse(text):
            result={}
            for line in text.splitlines():
                name,version=line.split('\t');name=name.removesuffix(':amd64')
                if name in result:raise ValueError('Ambiguous native package inventory')
                result[name]=version
            return result
        a,b=parse(before),parse(after)
        return sorted(({'package':n,'installed':a.get(n),'candidate':b.get(n)} for n in set(a)|set(b) if a.get(n)!=b.get(n)),key=lambda r:r['package'])
    a,b=set(before.splitlines()),set(after.splitlines())
    return {'removed':sorted(a-b),'added':sorted(b-a)}


def build(row, *, resume=False):
    name=row['component'];family=row['family'];parent=row['parent_image']
    directory=ROOT/'build-contexts'/name
    if not resume:directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    elif not directory.is_dir():raise ValueError('Existing reviewed context required')
    if resume and (directory/'built.json').exists():
        accepted=json.loads((directory/'built.json').read_text())
        for package,digest in accepted['packages_sha256'].items():
            if sha(directory/'packages'/package)!=digest:raise ValueError('Accepted package changed')
        if sha(directory/'Dockerfile')!=accepted['dockerfile_sha256']:raise ValueError('Accepted recipe changed')
        image=json.loads(probe.run(['docker','image','inspect',accepted['image']],capture_output=True,text=True).stdout)[0]
        if image['Id']!=accepted['image']:raise ValueError('Accepted candidate missing')
        return accepted
    changes=row['changes']
    expected=sorted(changes,key=lambda r:r['package'])
    requirements=[r['package']+'='+r['candidate'] for r in changes]
    container='hc-update-download-'+name+'-20261103'
    command=['docker','run','--rm','--name',container,'--label',probe.LABEL,'--network','bridge',
        '--user','0:0','--entrypoint','sh','--cap-drop','ALL',
        '--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--cap-add','FOWNER','--cap-add','SETUID','--cap-add','SETGID',
        '--security-opt','no-new-privileges','--memory','1g','--cpus','1','--pids-limit','128',
        '--mount','type=bind,src='+str(directory)+',dst=/artifacts',parent,'-c',COLLECT,'hc-package-collect',*requirements]
    if not resume:
        try:
            with (directory/'download.log').open('w') as stream:probe.run(command,stdout=stream,stderr=stream,timeout=900)
        except BaseException:
            subprocess.run(['docker','rm','-f',container],capture_output=True);raise
    fresh=sorted(probe.parse_changes(family,(directory/'transactions.txt').read_text()),key=lambda r:r['package'])
    if fresh!=expected:raise ValueError('Signed catalog plan changed; review before building')
    files=sorted((directory/'packages').iterdir())
    if not files:raise ValueError('Missing package archives')
    if family=='debian':
        spec=importlib.util.spec_from_file_location('package_verification',BASE/'maintenance/host-update-20261103/source/plan.py')
        verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
        metadata=(directory/'packages.metadata').read_text()
        for file in files:
            fields=verify.deb822(subprocess.check_output(['dpkg-deb','--field',str(file)],text=True))[0]
            record=verify.metadata(metadata,fields['Package'],fields['Version'],fields['Architecture'])
            verify.verify_deb(file,record)
    info=json.loads(probe.run(['docker','image','inspect',parent],capture_output=True,text=True).stdout)[0]
    if info['Architecture']!='amd64':raise ValueError('Only the reviewed amd64 inventory is supported')
    parent_tag='hc-container-update-'+name+'-parent:20261103'
    candidate='hc-container-update-'+name+':20261103'
    existing=subprocess.run(['docker','image','inspect',parent_tag],capture_output=True,text=True)
    if existing.returncode==0 and json.loads(existing.stdout)[0]['Id']!=parent:raise ValueError('Parent tag collision')
    if subprocess.run(['docker','image','inspect',candidate],capture_output=True).returncode==0:raise ValueError('Candidate already exists')
    probe.run(['docker','tag',parent,parent_tag],capture_output=True)
    if family=='debian':
        install='DEBIAN_FRONTEND=noninteractive dpkg --force-confold --install /tmp/hc-update/*.deb'
        inventory="dpkg-query -W -f='${binary:Package}\\t${Version}\\n' | sort"
    else:
        install='apk --no-network add --upgrade /tmp/hc-update/*.apk'
        inventory='apk info -v | sort'
    user=info['Config'].get('User') or '0:0'
    recipe=f'FROM {parent_tag}\nUSER 0:0\nCOPY packages/ /tmp/hc-update/\nRUN {install} && mkdir -p /opt/hc-container-update && {inventory} > /opt/hc-container-update/os.lock && rm -rf /tmp/hc-update\nUSER {user}\n'
    if resume and (directory/'Dockerfile').exists():shutil.copyfile(directory/'Dockerfile',directory/'Dockerfile.failed-apt')
    (directory/'Dockerfile').write_text(recipe)
    hashes={p.name:sha(p) for p in files}
    with (directory/('build-2.log' if resume else 'build.log')).open('w') as stream:
        probe.run(['docker','build','--network','none','--pull=false','-t',candidate,str(directory)],stdout=stream,stderr=stream,timeout=900)
    built=json.loads(probe.run(['docker','image','inspect',candidate],capture_output=True,text=True).stdout)[0]
    for field in ('Entrypoint','Cmd','Env','WorkingDir','ExposedPorts','Volumes','Healthcheck'):
        if built['Config'].get(field)!=info['Config'].get(field):raise ValueError('Image startup configuration changed: '+field)
    after=probe.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                     '--entrypoint','cat',built['Id'],'/opt/hc-container-update/os.lock'],capture_output=True,text=True,timeout=60).stdout
    (directory/'after.lock').write_text(after)
    delta=inventory_difference(family,(directory/'before.lock').read_text(),after)
    if family=='debian':
        if delta!=expected:raise ValueError('Built Debian package delta differs')
    else:
        wanted={'removed':sorted(r['package']+'-'+r['installed'] for r in changes if r['installed']),
                'added':sorted(r['package']+'-'+r['candidate'] for r in changes)}
        if delta!=wanted:raise ValueError('Built Alpine package delta differs')
    result={'ok':True,'component':name,'parent_image':parent,'image':built['Id'],'tag':candidate,
            'family':family,'changes':changes,'packages_sha256':hashes,'dockerfile_sha256':sha(directory/'Dockerfile'),
            'before_lock_sha256':sha(directory/'before.lock'),'after_lock_sha256':sha(directory/'after.lock'),
            'build_network':'none','startup_config_preserved':True,'deployment_performed':False}
    (directory/'built.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    plan=json.loads((ROOT/'os-upgrade-plan-complete.json').read_text())
    if not plan['ok']:raise ValueError('Incomplete source package plan')
    selected=[r for r in plan['components'].values() if r['changes']]
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(build,r,resume=args.resume) for r in selected]):
            result=future.result();results.append(result)
            (ROOT/'built-os-images.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps({'component':result['component'],'image':result['image'],'ok':True}),flush=True)


if __name__=='__main__':main()
