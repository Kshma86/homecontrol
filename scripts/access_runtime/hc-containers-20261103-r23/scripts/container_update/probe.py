#!/usr/bin/env python3
"""Fresh signed package planning in disposable containers, never live roots."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = Path('/srv/docker/homecontrol')
ROOT = BASE / 'maintenance/container-update-20261103'
LABEL = 'hc.container-update=20261103'
ATTEMPT = 1


def run(args, **kwargs):
    env = {k:v for k,v in os.environ.items() if k not in
           ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    env['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
    return subprocess.run(args, check=True, env=env, **kwargs)


def parse_changes(family, text):
    rows = []
    for line in text.splitlines():
        if family == 'debian':
            if line.startswith('Remv '): raise ValueError('Package removal is outside scope')
            if not line.startswith('Inst '): continue
            match = re.fullmatch(r'Inst ([\w.+:-]+) (?:\[([^\]]+)\] )?\((\S+) .+\)\s*(?:\[[^\]]*\])?', line)
            if not match: raise ValueError('Unrecognized APT transaction')
            rows.append({'package':match[1], 'installed':match[2], 'candidate':match[3]})
        else:
            if re.search(r'\b(Purging|Removing|Downgrading)\b', line): raise ValueError('Unsafe APK transaction')
            if not re.search(r'\b(Upgrading|Installing)\b', line): continue
            match = re.fullmatch(r'\(\d+/\d+\) (Upgrading|Installing) ([\w.+-]+) \(([^()]*)\)',line)
            if not match: raise ValueError('Unrecognized APK transaction')
            versions = match[3].split(' -> ')
            if len(versions) != (2 if match[1]=='Upgrading' else 1): raise ValueError('Ambiguous APK versions')
            rows.append({'package':match[2], 'installed':versions[0] if len(versions)==2 else None,
                         'candidate':versions[-1]})
    if len({r['package'] for r in rows}) != len(rows): raise ValueError('Duplicate package transaction')
    return rows


SCRIPT = r'''set -eu
if command -v apt-get >/dev/null; then
  echo debian > /artifacts/family
  dpkg-query -W -f='${binary:Package}\t${Version}\n' | sort > /artifacts/before.lock
  mkdir -p /tmp/lists/partial /tmp/cache/archives/partial
  apt-get -o Dir::State::Lists=/tmp/lists -o Dir::Cache=/tmp/cache -o APT::Update::Error-Mode=any update
  apt-get -o Dir::State::Lists=/tmp/lists -o Dir::Cache=/tmp/cache --simulate --no-remove --with-new-pkgs upgrade > /artifacts/transactions.txt
  cat /etc/os-release > /artifacts/os-release
elif command -v apk >/dev/null; then
  echo alpine > /artifacts/family
  apk info -v | sort > /artifacts/before.lock
  # apk takes its database lock even for index refresh. Give it a copied
  # database/world/key set, keeping the parent filesystem read-only.
  mkdir -p /tmp/apkroot/lib /tmp/apkroot/etc /tmp/apkroot/var/cache/apk /tmp/apkroot/var/log
  cp -a /lib/apk /tmp/apkroot/lib/
  cp -a /etc/apk /tmp/apkroot/etc/
  apk --root /tmp/apkroot update
  apk --root /tmp/apkroot upgrade --simulate > /artifacts/transactions.txt
  cat /etc/os-release > /artifacts/os-release
else
  echo Unsupported distribution >&2; exit 1
fi
chown -R 1000:1000 /artifacts
'''


def probe(row):
    name = row['Name'].lstrip('/')
    directory = ROOT / ('os-probes' if ATTEMPT == 1 else 'os-probes-' + str(ATTEMPT)) / name
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    container = 'hc-update-probe-' + name + '-20261103-' + str(ATTEMPT)
    command = ['docker','run','--rm','--name',container,'--label',LABEL,
        '--network','bridge','--read-only','--user','0:0','--entrypoint','sh',
        '--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE','--cap-add','FOWNER',
        '--cap-add','SETUID','--cap-add','SETGID',
        '--security-opt','no-new-privileges','--memory','768m','--cpus','1','--pids-limit','128',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=256m',
        '--tmpfs','/var/log:rw,nosuid,nodev,size=8m',
        '--mount','type=bind,src='+str(directory)+',dst=/artifacts', row['Image'],'-c',SCRIPT]
    try:
        with (directory/'probe.log').open('w') as stream:
            run(command,stdout=stream,stderr=stream,timeout=600)
        family = (directory/'family').read_text().strip()
        if family not in ('debian','alpine'): raise ValueError('Unknown distro')
        changes = parse_changes(family,(directory/'transactions.txt').read_text())
        result = {'ok':True,'component':name,'parent_image':row['Image'],'family':family,'changes':changes,
                  'live_container_modified':False,'packages_installed':False,'signed_catalog_refresh':True}
    except Exception as error:
        # The exact unique probe name belongs to this run. Do not touch peers.
        subprocess.run(['docker','rm','-f',container],capture_output=True)
        result = {'ok':False,'component':name,'parent_image':row['Image'],'error_type':type(error).__name__}
    (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    global ATTEMPT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--components',nargs='+');args=parser.parse_args()
    if args.attempt < 1: raise ValueError('Positive attempt number required')
    ATTEMPT=args.attempt
    report=ROOT/('os-upgrade-plan.json' if ATTEMPT==1 else 'os-upgrade-plan-'+str(ATTEMPT)+'.json')
    if report.exists(): raise ValueError('Attempt already recorded; preserve its result')
    os.umask(0o077)
    if ATTEMPT==1: ROOT.mkdir(mode=0o700,exist_ok=False)
    elif not (ROOT/'baseline.json').is_file(): raise ValueError('Existing baseline required for retry')
    accepted = json.loads((BASE/'backups/releases/hc-audit-20261103-r22/evidence/post-live-check.json').read_text())
    rows = json.loads(run(['docker','inspect',*accepted['containers']],capture_output=True,text=True).stdout)
    for row in rows:
        before = accepted['containers'][row['Name'].lstrip('/')]
        if row['Id'] != before['id'] or row['Image'] != before['image'] or row['State']['Running'] != before['running']:
            raise ValueError('Current release baseline changed')
    baseline={'release':'hc-audit-20261103-r22','captured_at':datetime.now(timezone.utc).isoformat(),
        'containers':{r['Name'].lstrip('/'):{'id':r['Id'],'image':r['Image'],'running':r['State']['Running']} for r in rows},
        'compose_sha256':hashlib.sha256((BASE/'infra/docker-compose.yml').read_bytes()).hexdigest()}
    if ATTEMPT==1: (ROOT/'baseline.json').write_text(json.dumps(baseline,indent=2)+'\n')
    else:
        original=json.loads((ROOT/'baseline.json').read_text())
        if any(baseline[k]!=original[k] for k in ('release','containers','compose_sha256')):
            raise ValueError('Baseline changed since first attempt')
    results = []
    selected=[row for row in rows if row['State']['Running']]
    if args.components:
        if set(args.components)-{row['Name'].lstrip('/') for row in selected}: raise ValueError('Unknown active component')
        selected=[row for row in selected if row['Name'].lstrip('/') in args.components]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(probe,row) for row in selected]
        for future in as_completed(futures):
            result = future.result(); results.append(result)
            report.write_text(json.dumps({'complete':False,'components':results},indent=2)+'\n')
            print(json.dumps({'component':result['component'],'ok':result['ok'],'updates':len(result.get('changes',[]))}),flush=True)
    result = {'complete':True,'ok':all(r['ok'] for r in results),'components':sorted(results,key=lambda r:r['component']),
              'deployment_performed':False,'private_inventory_uploaded':False}
    report.write_text(json.dumps(result,indent=2)+'\n')
    return 0 if result['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
