#!/usr/bin/env python3
"""One local sudo transaction for the sealed r19 audit completion package."""
import importlib.util,json,os,signal,sys
from pathlib import Path
BASE=Path('/srv/docker/homecontrol');NAME='hc-audit-20261102-r19';KIT=BASE/'backups/releases'/NAME
sys.dont_write_bytecode=True
sys.path.insert(0,str(KIT/'source/scripts/router_release'))
spec=importlib.util.spec_from_file_location('audit_router_activation',KIT/'source/scripts/router_release/activate.py')
router=importlib.util.module_from_spec(spec);spec.loader.exec_module(router)

def probes():
 spec=importlib.util.spec_from_file_location('audit_readonly_platform_probes',KIT/'source/scripts/security_release/activate.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def platform_checks(manifest,previous=False):
 # Reuse only the read-only HA API and PG locale probes. HA and PostgreSQL are
 # not stopped, copied, upgraded or recreated by this three-component release.
 sys.path.insert(0,str(KIT/'source/scripts/security_release'))
 check=probes();core=router.core
 ha=check.ha_ready(core,manifest,previous=previous)
 pg=check.postgres_ready(core)
 changed={core.container(n) for n in manifest['changed_services']}
 for name,wanted in manifest['baseline'].items():
  if name in changed:continue
  row=json.loads(core.call(['docker','inspect',name]).stdout)[0]
  if row['Id']!=wanted['id'] or row['Image']!=wanted['image']:raise ValueError('Unchanged component replaced: '+name)
 proof={'ok':True,'ha':ha,'postgres':pg,'unchanged_components':len(manifest['baseline'])-len(changed)}
 core.platform().write_json(KIT/'evidence'/('platform-before.json' if previous else 'platform-live.json'),proof,0o644)
 return proof

def complete(core):
 sys.path.insert(0,str(KIT/'source/scripts/audit_release'))
 from postcheck import capture,finish
 manifest=core.load()
 try:live=capture(core,manifest,final=True)
 except BaseException:
  core.rollback(manifest);raise
 finish(core,live=live)

def main(action='activate'):
 if os.geteuid()!=0:raise PermissionError('Local sudo is required; never use Docker to bypass host secret permissions')
 core=router.core
 if action=='activate':
  manifest=core.verify();core.guard_runtime(manifest);platform_checks(manifest,previous=True)
  original=core.Cutover.verify
  def verify(context):
   original(context);platform_checks(manifest)
  core.Cutover.verify=verify
  original_proof=router.full_proof
  def proof(m):
   result=original_proof(m)
   sys.path.insert(0,str(KIT/'source/scripts/audit_release'))
   from postcheck import capture
   capture(core,m)
   return result
  router.full_proof=proof
 result=router.main(action)
 if action=='activate':complete(core)
 return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('activate','rollback'),nargs='?',default='activate');a=p.parse_args()
 signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(InterruptedError('Terminated')))
 try:main(a.action)
 except BaseException as error:
  if os.geteuid()==0:
   try:router.core.platform().write_json(KIT/'private/audit-error.json',{'error_type':type(error).__name__,'detail':str(error)})
   except Exception:pass
  print('Az r19 művelet megállt: '+type(error).__name__+'. Napló: private/audit-error.json és deployment-status.json; ne ismételd vakon az aktiválást.',file=sys.stderr);raise SystemExit(1)
