#!/usr/bin/env python3
"""Run an offline HA recorder migration on a private copy; never mount live config."""
import argparse
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import re,shutil,sqlite3,subprocess,time,uuid


def call(args,**kwargs):return subprocess.run(args,check=True,**kwargs)


def db_info(path):
 with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
  if db.execute('pragma quick_check').fetchall()!=[('ok',)]:raise ValueError('Recorder integrity failed')
  tables={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
  return {'schema':db.execute('select max(schema_version) from schema_changes').fetchone()[0],
          'rows':{n:db.execute('select count(*) from "'+n+'"').fetchone()[0] for n in ('states','events','statistics') if n in tables}}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',required=True)
 p.add_argument('--input',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
 p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 if not re.fullmatch(r'sha256:[0-9a-f]{64}',a.image):raise ValueError('Use an exact local image ID')
 if a.work.exists() or a.work.is_symlink() or a.input.is_symlink():raise ValueError('Use a new private work directory')
 if a.work.resolve().is_relative_to(Path('/srv/docker/homecontrol/homeassistant')):raise ValueError('Never probe in live configuration')
 for path in a.input.rglob('*'):
  if path.is_symlink() or not(path.is_file() or path.is_dir()):raise ValueError('Unexpected config file type')
 a.work.mkdir(mode=0o700,parents=True)
 config=a.work/'config';shutil.copytree(a.input,config)
 text=(config/'configuration.yaml').read_text()
 if re.search(r'^recorder\s*:',text,re.M):raise ValueError('Existing recorder configuration requires an explicit test adapter')
 (config/'configuration.yaml').write_text(text+'\nrecorder:\n  auto_purge: false\n')
 (config/'.ha_run.lock').unlink(missing_ok=True)
 before=db_info(config/'home-assistant_v2.db')
 schema_code='import homeassistant.components.recorder.db_schema as d; print(d.SCHEMA_VERSION)'
 expected=int(subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','python',a.image,'-B','-c',schema_code],text=True))
 name='hc-ha-migration-'+uuid.uuid4().hex[:12]
 user=str(os.geteuid())+':'+str(os.getegid())
 report={'ok':False,'started_at':datetime.now(timezone.utc).isoformat(),'image':a.image,'before':before,
         'expected_schema':expected,'network':'none','production_config_mounted':False,'physical_integrations_verified':False}
 call(['docker','run','-d','--name',name,'--label','hc.audit=hc23-43-ha','--network','none',
       '--user',user,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
       '--memory','2g','--cpus','2','--pids-limit','256','--tmpfs','/tmp:rw,nosuid,nodev,size=256m',
       '--env','HOME=/config','--env','PYTHONDONTWRITEBYTECODE=1','--mount','type=bind,src='+str(config.resolve())+',dst=/config',
       '--entrypoint','python',a.image,'-m','homeassistant','--config','/config','--skip-pip'],stdout=subprocess.DEVNULL)
 try:
  query='import urllib.request,urllib.error;\ntry:r=urllib.request.urlopen("http://127.0.0.1:8123/api/",timeout=2);print(r.status)\nexcept urllib.error.HTTPError as e: print(e.code)'
  for _ in range(120):
   live=subprocess.run(['docker','exec',name,'python','-c',query],capture_output=True,text=True)
   try:current=db_info(config/'home-assistant_v2.db')
   except (ValueError,sqlite3.Error):current=None
   if live.returncode==0 and live.stdout.strip() in ('200','401') and current and current['schema']==expected:
    if all(current['rows'][n]>=count for n,count in before['rows'].items()):
     report.update(ok=True,http_status=int(live.stdout.strip()),after=current,rows_preserved=True);break
   status=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]['State']
   if not status['Running']:raise RuntimeError('Candidate Home Assistant exited')
   time.sleep(2)
  else:raise TimeoutError('Candidate recorder migration / HTTP probe did not complete')
 finally:
  logs=subprocess.run(['docker','logs',name],capture_output=True)
  (a.work/'private-ha.log').write_bytes(logs.stdout+logs.stderr);(a.work/'private-ha.log').chmod(0o600)
  call(['docker','rm','-f',name],stdout=subprocess.DEVNULL)
  report['finished_at']=datetime.now(timezone.utc).isoformat()
  a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report));return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
