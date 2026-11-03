#!/usr/bin/env python3
"""Offline OS/license scan of an explicit candidate lock, with narrow mounts."""
import collections,json,subprocess,time
from pathlib import Path
B=Path('/srv/docker/homecontrol');OUT=B/'docs/audit-evidence/hc23-43-20261102'
WORK=Path('/tmp/hc23-43-20261102/scan');CACHE=WORK.parent/'trivy-cache'
WORK.mkdir(exist_ok=True)
lock=json.loads((OUT/'candidate-image-lock.json').read_text())
scanner=json.loads(subprocess.check_output(['docker','image','inspect','aquasec/trivy:0.76.0'],text=True))[0]
metadata=json.loads((CACHE/'db/metadata.json').read_text());assert metadata['DownloadedAt'][:10]=='2026-11-02'
rows=[]
for name,image in lock.items():
 archive=WORK/'image.tar';raw=WORK/(name+'.json');log=WORK/(name+'.log');start=time.monotonic()
 subprocess.run(['docker','image','save','-o',str(archive),image],check=True,timeout=300)
 command=['docker','run','--rm','--name','hc43-candidate-scan-20261102','--label','hc.audit=hc23-43-20261102',
 '--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges',
 '--cpus','1','--memory','2g','--pids-limit','128','--tmpfs','/tmp:rw,nosuid,nodev,size=768m',
 '--mount','type=bind,src='+str(archive)+',dst=/image.tar,readonly',
 '--mount','type=bind,src='+str(WORK)+',dst=/out',
 '--mount','type=bind,src='+str(CACHE)+',dst=/cache',scanner['Id'],'image','--cache-dir','/cache',
 '--skip-db-update','--skip-java-db-update','--offline-scan','--disable-telemetry','--scanners','vuln,license','--pkg-types','os',
 '--timeout','10m','--no-progress','--format','json','--output','/out/'+raw.name,'--input','/image.tar']
 with log.open('w') as stream:subprocess.run(command,stdout=stream,stderr=stream,check=True,timeout=660)
 data=json.loads(raw.read_text());v=[x for r in data.get('Results',[]) for x in r.get('Vulnerabilities',[])]
 row={'name':name,'image':image,'seconds':round(time.monotonic()-start,1),'os':data.get('Metadata',{}).get('OS'),
 'records':len(v),'severity':dict(collections.Counter(x['Severity'] for x in v)),
 'fixed_available':sum(bool(x.get('FixedVersion')) for x in v),
 'findings':[{k:x.get(k) for k in ('VulnerabilityID','PkgName','InstalledVersion','FixedVersion','Severity','Status','PrimaryURL')} for x in v]}
 rows.append(row);archive.unlink()
 report={'ok':len(rows)==len(lock),'completed_images':len(rows),'expected_images':len(lock),
 'scanner_image':scanner['Id'],'scanner_repo_digests':scanner['RepoDigests'],'database':metadata,
 'offline_scan':True,'inventory_uploaded':False,'images':rows}
 (OUT/'os-candidate-advisories.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k!='findings'}),flush=True)
