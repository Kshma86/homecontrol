"""One local sudo entrypoint: approved cloud smoke, acceptance, then guarded deploy."""
import json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import deploy as release
import cloud_smoke

def accept_cloud():
 p=release.platform();m=release.load();e=release.KIT/'evidence'
 approval=json.loads((e/'xiaomi-approval.json').read_text())
 if approval.get('saved_xiaomi_session_use') is not True or approval.get('robot_commands') is not False:
  raise ValueError('Explicit Xiaomi approval required')
 result=json.loads((e/'x10-cloud.json').read_text())
 if not (result.get('ok') is True and result.get('robot_commands_sent') is False
         and result.get('cloud_tls_and_saved_session') is True
         and result.get('map_downloaded_and_json_decoded') is True):
  raise ValueError('Authenticated Xiaomi map smoke has not passed')
 report=json.loads((e/'acceptance.json').read_text())
 report.update(ok=True,pending=[],authenticated_xiaomi_cloud_smoke=True)
 report['evidence_sha256'].update({'x10-cloud.json':release.digest(e/'x10-cloud.json')})
 p.write_json(e/'acceptance.json',report,0o644)
 m.update(acceptance_sha256=release.digest(e/'acceptance.json'),ready_for_root_deploy=True,
          status='ready_for_root_deploy_not_deployed')
 p.write_json(release.KIT/'release.json',m,0o644)

def main():
 if os.geteuid()!=0:raise PermissionError('Run this command with sudo in the HC local terminal')
 p=release.platform()
 p.no_symlinks(release.KIT/'private/operator.lock')
 with (release.KIT/'private/operator.lock').open('a') as lock:
  release.fcntl.flock(lock,release.fcntl.LOCK_EX|release.fcntl.LOCK_NB)
  m=release.verify(allow_cloud_pending=True)
  approval=json.loads((release.KIT/'evidence/xiaomi-approval.json').read_text())
  if approval.get('saved_xiaomi_session_use') is not True:raise ValueError('Missing user approval')
  release.guard_runtime(m)
  release.phase('approved_xiaomi_cloud_smoke')
  cloud_smoke.main()
  accept_cloud()
  def terminate(signum,frame):raise InterruptedError('Operator terminated the cutover')
  release.signal.signal(release.signal.SIGTERM,terminate)
  release.deploy()
 print(json.dumps({'action':'activate','success':True}))

if __name__=='__main__':
 try:main()
 except Exception as exc:
  if os.geteuid()==0:
   release.platform().write_json(release.KIT/'private/error.json',{'error_type':type(exc).__name__,'detail':str(exc),'time':release.time.time()})
   release.platform().write_json(release.KIT/'deployment-status.json',{'state':'stopped','error_type':type(exc).__name__},0o644)
  raise SystemExit('r12 activation stopped ('+type(exc).__name__+'); inspect private/progress.json and private/error.json')
