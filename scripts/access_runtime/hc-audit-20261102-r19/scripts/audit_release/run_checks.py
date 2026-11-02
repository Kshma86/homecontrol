"""Run the existing isolated profiles against the exact frozen r19 tree."""
import hashlib,json,shutil,sys
from pathlib import Path
BASE=Path('/srv/docker/homecontrol');KIT=BASE/'backups/releases/hc-audit-20261102-r19'
sys.path.insert(0,str(BASE/'scripts'));import check_hc_tests as checks

def frozen_stage(output,profile='deployed'):
 assert output.parent==Path('/tmp') and not output.exists()
 shutil.copytree(KIT/'source',output,ignore=shutil.ignore_patterns('__pycache__'))
 changes=[]
 if profile=='standard':
  policy=output/'infra/backend/deployment_policy.py';text=policy.read_text();assert 'POLICY_REQUIRED = True' in text
  policy.write_text(text.replace('POLICY_REQUIRED = True','POLICY_REQUIRED = False',1));(output/'infra/backend/deployment_policy.json').unlink(missing_ok=True)
  changes=['optional policy only in disposable generic-contract test source']
 receipt={'release':'hc-audit-20261102-r19','policy_profile':profile,'test_only_changes':changes,'production_changed':False,
 'source_sha256':{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}}
 (output/'.hc-test-source.json').write_text(json.dumps(receipt,indent=2)+'\n');return output
checks.stage=frozen_stage
if __name__=='__main__':raise SystemExit(checks.main())
