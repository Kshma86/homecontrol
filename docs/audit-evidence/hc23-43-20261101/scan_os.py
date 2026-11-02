#!/usr/bin/env python3
"""Scan the captured running image IDs offline, one temporary archive at a time."""
import collections,hashlib,json,subprocess,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
WORK=Path('/tmp/hc23-43-20261101'); CACHE=WORK/'trivy-cache'
base=json.loads((OUT/'before.json').read_text())
scanner=json.loads(subprocess.check_output(['docker','image','inspect','aquasec/trivy:0.76.0'],text=True))[0]
metadata=json.loads((CACHE/'db/metadata.json').read_text())
assert metadata['UpdatedAt'][:10]=='2026-11-01'
summary=[]
for i,(name,item) in enumerate(base['containers'].items()):
 if item['status']!='running':continue
 archive=WORK/'scan-image.tar';result=WORK/(name+'-os.json');log=WORK/(name+'-os.log')
 start=time.monotonic()
 subprocess.run(['docker','image','save','-o',str(archive),item['image']],check=True,timeout=300)
 args=['docker','run','--rm','--name','hc43-os-scan-20261101','--label','hc.audit=hc23-43-20261101',
 '--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges',
 '--cpus','1','--memory','2g','--pids-limit','128','--tmpfs','/tmp:rw,nosuid,nodev,size=768m',
 '--mount','type=bind,src='+str(WORK)+',dst=/work',scanner['Id'],'image','--cache-dir','/work/trivy-cache',
 '--skip-db-update','--skip-java-db-update','--offline-scan','--disable-telemetry','--scanners','vuln,license',
 '--pkg-types','os','--timeout','10m','--no-progress','--format','json','--output','/work/'+result.name,'--input','/work/'+archive.name]
 with log.open('w') as stream:r=subprocess.run(args,stdout=stream,stderr=stream,timeout=660)
 row={'name':name,'image':item['image'],'exit':r.returncode,'seconds':round(time.monotonic()-start,1)}
 if not r.returncode:
  data=json.loads(result.read_text());v=[x for z in data.get('Results',[]) for x in z.get('Vulnerabilities',[])]
  row.update(os=data.get('Metadata',{}).get('OS'),records=len(v),unique_ids=len({x['VulnerabilityID'] for x in v}),
   severity=dict(collections.Counter(x['Severity'] for x in v)),fixed_available=sum(bool(x.get('FixedVersion')) for x in v),
   findings=[{k:x.get(k) for k in ('VulnerabilityID','PkgName','InstalledVersion','FixedVersion','Severity','Status','PrimaryURL')} for x in v])
 else:raise RuntimeError('Offline image scan failed: '+name)
 summary.append(row);archive.unlink()
 report={'ok':True,'scanner_image':scanner['Id'],'scanner_repo_digests':scanner['RepoDigests'],'database':metadata,'offline_scan':True,'inventory_uploaded':False,'images':summary}
 (OUT/'os-advisories.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k!='findings'}),flush=True)
