"""Restore stopped r10 after the specific r11 lock-adapter import failure.

Does not deploy r11 or recreate infrastructure. Requires actual local sudo.
"""
import fcntl,hashlib,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import deploy as release

ORIGINAL_DEPLOY_SHA='955d7dd30ec9a8831e00e957b0dbd149608703587e9e02e0eaa5f82ad3228bca'
PATCHED_DEPLOY_SHA='3606120fc3c755539f3eb908b085c7434a327cccaed1fa16e11996d65f781236'

def main():
 if os.geteuid()!=0:raise PermissionError('Local sudo required for recovery')
 p=release.platform();m=release.load()
 if json.loads((release.BASE/'infra/access-release.json').read_text()).get('release')!=release.OLD:
  raise ValueError('This recovery only applies before installation of r11')
 if release.digest(release.BASE/'infra/docker-compose.yml')!=m['previous_compose_sha256']:
  raise ValueError('Previous Compose differs; manual reconciliation required')
 if release.RUNTIME.exists() or release.PRIVATE.exists():raise ValueError('Unexpected installed r11 runtime')
 if m['source_sha256']['scripts/f10_release/deploy.py']!=ORIGINAL_DEPLOY_SHA:
  raise ValueError('Not the known affected deployment')
 for name,sha in m['source_sha256'].items():
  path=release.KIT/'source'/name;p.no_symlinks(path)
  expected=PATCHED_DEPLOY_SHA if name=='scripts/f10_release/deploy.py' else sha
  if release.digest(path)!=expected:raise ValueError('Unexpected source change: '+name)
 error=json.loads((release.KIT/'private/error.json').read_text())
 if error.get('error_type')!='AttributeError' or 'locked' not in error.get('detail',''):
  raise ValueError('This is not the diagnosed lock-adapter failure')
 state=json.loads((release.STATE/'transition.json').read_text())
 if state.get('release')!=release.NAME:raise ValueError('Wrong transition')
 # All applications remain on their old images; no replacements may be adopted.
 for name,expected in m['baseline'].items():
  row=json.loads(release.call(['docker','inspect',name]).stdout)[0]
  if row['Id']!=expected['id'] or row['Image']!=expected['image']:
   raise ValueError('Unexpected runtime change: '+name)
 with (release.KIT/'private/operator.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  release.rollback(m)
  p.write_json(release.KIT/'private/recovery.json',{'success':True,'state':'r10_restored','r11_deployed':False,'cause':'wrong module for common lock adapter'})
 print(json.dumps({'action':'recover_r10','success':True,'r11_deployed':False}))

if __name__=='__main__':
 try:main()
 except Exception as exc:
  if os.geteuid()==0:release.platform().write_json(release.KIT/'private/recovery-error.json',{'type':type(exc).__name__,'detail':str(exc)})
  raise SystemExit('r10 recovery stopped ('+type(exc).__name__+'); inspect private/recovery-error.json')
