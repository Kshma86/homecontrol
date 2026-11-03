"""Seal r19 only after exact-source regression, baked code and rollback checks."""
import ast,json,re,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
from prepare import BASE,OLD,NAME,KIT,EVIDENCE,COMPONENTS,digest,read,write

def main():
 m=read(KIT/'release.json');assert not m['ready_for_root_deploy']
 assert read(BASE/'infra/access-release.json')['release']==OLD
 old=read(BASE/'backups/releases'/OLD/'release.json')
 assert all(digest(BASE/'scripts/access_runtime'/OLD/n)==h for n,h in old['source_sha256'].items())
 assert digest(BASE/'infra/docker-compose.yml')==m['previous_compose_sha256']
 assert digest(BASE/'HC_REFACTOR_AUDIT.md')=='51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2'
 rows=re.findall(r'^\| (HC-\d+) \|.*?\| ([^|]+) \|$',(BASE/'AUDIT_REPAIR.md').read_text(),re.M)
 assert len(rows)==48 and {n for n,v in rows}=={'HC-'+str(i).zfill(2) for i in range(1,49)}
 assert sum(v.strip()=='Ellenőrzött' for n,v in rows)==46
 assert {n for n,v in rows if v.strip()=='Folyamatban'}=={'HC-41','HC-43'}
 counts={};selected={};ids=set();frontend=0
 for profile in ('unit','ownership','deployed','postgres','frontend','bridges','ingest','x10','mdns','growatt'):
  folder='recheck-'+profile if profile in ('unit','bridges','ingest','x10') else 'regression'
  report=read(KIT/'evidence'/folder/'test-summary.json');row=report['profiles'][profile];assert row['ok'],profile
  rows=list(row['modules'].values()) if profile=='postgres' else [row]
  count=0
  for item in rows:
   r=item['result'];assert item['returncode']==0 and not any(r[n] for n in ('failures','errors','skipped'))
   count+=r['tests'];ids.update(t.removeprefix('tests.') for t in r.get('test_ids',[]))
  if profile=='frontend':frontend=count
  elif profile in ('bridges','ingest','x10'):
   text=(KIT/'evidence'/folder/row['log']).read_text();found=re.findall(r'^test\S+ \(([^\n()]+)\) \.\.\.',text,re.M);assert len(found)==count;ids.update(found)
  counts[profile]=count;selected[profile]=folder+'/test-summary.json'
  # These are the exact shipped runtime inputs; optional policy is changed only
  # in the disposable generic-contract variant, as recorded by the runner.
  for service,(source,_) in COMPONENTS.items():
   for p in (KIT/'source'/source).glob('*.py'):
    n=str(p.relative_to(KIT/'source'))
    assert report['source_policies']['deployed']['source_sha256'][n]==digest(p),(profile,n)
 assert counts['unit']>=818 and counts['postgres']>=198 and counts['frontend']>=114
 assert len(ids)+frontend==1308
 for label,count in [('installer',16),('router',12),('audit-activation-final',13)]:
  text=(KIT/'evidence'/(label+'-tests.log')).read_text();assert re.search(r'Ran '+str(count)+r' tests in ',text) and text.rstrip().endswith('OK'),label
  counts[label]=count
 assert read(KIT/'evidence/baked-code-and-packages.json')['ok']
 process=read(KIT/'evidence/process-lab.json');assert process['network']=='none' and len(process['results'])==2
 for name,r in process['results'].items():
  assert r['running']
  if name=='backend':assert r['http']['/health/live']==200 and r['http']['/health/ready']==503
  else:assert r['live_exit']==0 and r['ready_exit']==1
 offline=read(KIT/'evidence/offline-load.json');assert offline['ok'] and set(offline['verified_images'])==set(m['recovery_images'])
 assert digest(KIT/'private/access-images.tar.gz')==m['offline_image_archive_sha256']==offline['archive_sha256']
 assert digest(KIT/'tools/rclone')==m['rclone_sha256']
 for name,h in read(KIT/'evidence/build-inputs.json')['sha256'].items():assert digest(KIT/'build-inputs'/name)==h
 for container,row in m['baseline'].items():
  actual=json.loads(subprocess.check_output(['docker','inspect','--format','{"id":{{json .Id}},"image":{{json .Image}}}',container],text=True));assert actual==row,container
 # The earlier proof is preserved as an r18+recovery-fix proof, never relabelled
 # as a fresh r19 VM restore. Fresh r19 Git/router and DB restore are root gates.
 proof=BASE/'docs/audit-evidence/hc23-43-closure-20261102/bounded-lab/vm-acceptance.json'
 prior=read(proof);assert prior['ok'] and prior['reboot_verified']
 shutil.copyfile(proof,KIT/'evidence/prior-r18-recovery-proof.json')
 for file in ('reviewed-inputs.json','overlay-review.json'):shutil.copyfile(EVIDENCE/file,KIT/'evidence'/file)
 src=BASE/'docs/audit-evidence/hc23-43-closure-20261102'
 for file in ('residual-risk-review.json','user-hc43-decision.json'):shutil.copyfile(src/file,KIT/'evidence'/file)
 assert not read(KIT/'evidence/user-hc43-decision.json')['explicit_risk_acceptance']
 for p in (KIT/'source').rglob('*'):
  assert not p.is_symlink()
  if p.is_file() and p.suffix=='.py':ast.parse(p.read_bytes(),filename=str(p))
 subprocess.run(['bash','-n',str(KIT/'source/scripts/bootstrap_restore_v0_1.sh')],check=True)
 write(KIT/'evidence/final-regression.json',{'ok':True,'counts':counts,'selected_reports':selected,'unique_regression_tests':1308,'additional_transaction_tests':41,'historical_fixture_failures':'regression/test-summary.json; three zero-test profiles replaced by explicit successful rechecks','production_changed':False})
 m['source_sha256']={str(p.relative_to(KIT/'source')):digest(p) for p in sorted((KIT/'source').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
 hashes={str(p.relative_to(KIT/'evidence')):digest(p) for p in sorted((KIT/'evidence').rglob('*')) if p.is_file() and p.name!='acceptance.json'}
 receipt={'ok':True,'release':NAME,'state':'sealed_ready_for_local_sudo_not_deployed','sealed_at':datetime.now(timezone.utc).isoformat(),
 'production_changed':False,'counts':counts,'regression_unique_tests':1308,'transaction_tests':41,
 'hc41_closed':False,'hc43_closed':False,'required_local_root_gates':['existing-platform HA API/PG collation','router probe/full repository check','verified pre-cutover backup','three-component switch and rollback guards','fresh HC/Git/router backup and isolated PostgreSQL restore','all runtime hashes and five timers','audit handover documentation'],
 'fresh_r19_vm_restore_performed':False,'prior_recovery_proof':'prior-r18-recovery-proof.json','evidence_sha256':hashes}
 write(KIT/'evidence/acceptance.json',receipt)
 m.update(acceptance_sha256=digest(KIT/'evidence/acceptance.json'),ready_for_root_deploy=True,status='sealed_ready_for_local_sudo_not_deployed',deployed=False)
 write(KIT/'release.json',m)
 print(json.dumps({'release':NAME,'ready_for_root_deploy':True,'source_files':len(m['source_sha256']),'tests':1308,'transaction_tests':41,'deployed':False}))
if __name__=='__main__':main()
