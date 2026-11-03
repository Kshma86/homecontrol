#!/usr/bin/env python3
"""Scan public candidate image archives offline; never expose the Docker socket."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from python_tooling import COMPONENTS

ROOT=Path('/srv/docker/homecontrol/maintenance/container-update-20261103')
SCANNER='sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222'


def scan(item):
    component,image=item;work=ROOT/'final-scans'/component;work.mkdir(parents=True,mode=0o700)
    archive=work/'image.tar'
    with archive.open('wb') as stream:subprocess.run(['docker','save',image],stdout=stream,check=True,timeout=600)
    args=['docker','run','--rm','--network','none','--read-only','--user','1000:1000',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','1800m','--cpus','2',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=512m','--env','HOME=/tmp',
        '--mount','type=bind,src='+str(ROOT/'trivy-cache')+',dst=/cache,readonly',
        '--mount','type=bind,src='+str(work)+',dst=/work',SCANNER,'image',
        '--cache-dir','/cache','--cache-backend','memory','--skip-db-update','--skip-java-db-update',
        '--offline-scan','--scanners','vuln','--format','json','--output','/work/result.json','--input','/work/image.tar']
    with (work/'scan.log').open('w') as stream:subprocess.run(args,stdout=stream,stderr=stream,check=True,timeout=900)
    raw=json.loads((work/'result.json').read_text());findings=[]
    for result in raw.get('Results',[]):
        for value in result.get('Vulnerabilities',[]):
            findings.append({**{k:value.get(k) for k in ('VulnerabilityID','PkgName','InstalledVersion','FixedVersion','Severity','Status','PrimaryURL')},'target':result.get('Target')})
    archive.unlink()
    row={'component':component,'image':image,'vulnerability_records':len(findings),
         'severity':dict(Counter(v['Severity'] for v in findings)),
         'fix_available':sum(bool(v['FixedVersion']) for v in findings),'findings':findings}
    print(json.dumps({k:v for k,v in row.items() if k!='findings'}),flush=True);return row


if __name__=='__main__':
    lock=json.loads((ROOT/'candidate-image-lock-final.json').read_text())
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(scan,[(n,lock[n]) for n in COMPONENTS]))
    report={'complete':True,'inventory_uploaded':False,'network':'none','scanner':SCANNER,
        'database':json.loads((ROOT/'trivy-cache/db/metadata.json').read_text()),'images':rows}
    (ROOT/'final-image-scan-report.json').write_text(json.dumps(report,indent=2)+'\n')
