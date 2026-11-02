#!/usr/bin/env python3
"""Run HC regression profiles in disposable containers with synthetic inputs only."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from stage_hc_test_source import stage

ROOT=Path(__file__).resolve().parents[1]
LABEL='hc23-43-tests'
IMAGE_OVERRIDES={}
PG_MODULES={
 'test_database_runtime_postgres':('HC15','hc15_runtime_test'),
 'test_about_inventory_postgres':('HC48','hc48_inventory_test'),
 'test_baseline_postgres':('HC38','hc38_schema_test'),
 'test_combustion_safety_state_postgres':('HC06','hc06_state_test'),
 'test_db_privileges_postgres':('HC39','hc39_privilege_test'),
 'test_irrigation_admission_postgres':('HC04','hc04_admission_test'),
 'test_irrigation_recovery_postgres':('HC03','hc03_recovery_test'),
 'test_process_binding_postgres':('HC3536','hc3536_test'),
 'test_scheduler_audit_postgres':('HC08','hc08_audit_test'),
 'test_scheduler_feedback_postgres':('HC08','hc08_audit_test'),
 'test_startup_schema_postgres':('HC07','hc07_schema_test'),
}
PROFILES=('unit','ownership','deployed','postgres','frontend','bridges','ingest','x10','mdns')


def command(args,**kwargs):
 return subprocess.run(args,check=True,**kwargs)


def image(container):
 if container in IMAGE_OVERRIDES:return IMAGE_OVERRIDES[container]
 return json.loads(subprocess.check_output(['docker','inspect',container],text=True))[0]['Image']


def base_run(source, *, root=False, network='none'):
 args=['docker','run','--rm','--label','hc.audit='+LABEL,'--network',network,'--read-only',
       '--cap-drop','ALL','--security-opt','no-new-privileges','--user','0:0' if root else '1000:1000',
       '--pids-limit','256','--memory','1g','--cpus','2',
       '--tmpfs','/tmp:rw,exec,nosuid,nodev,size=512m',
       '--mount','type=bind,src='+str(source)+',dst=/src,readonly',
       '--env','PYTHONDONTWRITEBYTECODE=1','--env','HOME=/tmp','--env','PYTHONPATH=/src/infra/backend']
 if root:
  for cap in ('CHOWN','FOWNER','DAC_OVERRIDE','SETUID','SETGID'):args+=['--cap-add',cap]
 return args


def read_result(log):
 text=log.read_text()
 # A unittest progress line on stderr can precede stdout's JSON on the same
 # line. Decode the explicit record rather than assuming a line boundary.
 for match in reversed(list(re.finditer(r'\{"(?:profile|tests)"\s*:',text))):
  try:value=json.JSONDecoder().raw_decode(text[match.start():])[0]
  except ValueError:continue
  if isinstance(value,dict) and 'tests' in value and 'failures' in value:return value
 node=dict(re.findall(r'^[#ℹ]\s*(tests|pass|fail|cancelled|skipped)\s+(\d+)\s*$',text,re.M))
 if {'tests','fail','cancelled','skipped'} <= node.keys():
  return {'tests':int(node['tests']),'failures':int(node['fail']),
          'errors':int(node['cancelled']),'skipped':int(node['skipped'])}
 return None


def execute(args,log,timeout=900):
 with log.open('w') as stream:
  p=subprocess.run(args,stdout=stream,stderr=stream,timeout=timeout)
 result=read_result(log)
 ok=p.returncode==0 and result is not None and result['tests']>0 and not any(result[n] for n in ('failures','errors','skipped'))
 return {'ok':ok,'returncode':p.returncode,'log':log.name,'result':result}


def postgres(source,backend,pgimage,out,runid):
 expected={p.stem for p in (source/'infra/backend/tests').glob('test_*_postgres.py')}
 mapping={**PG_MODULES,**{n:('MOWER','hc_mower_test') for n in expected if n.startswith('test_mower_')}}
 if expected!=set(mapping):raise ValueError('PostgreSQL profile map needs explicit update')
 results={}
 for number,(module,(prefix,database)) in enumerate(sorted(mapping.items())):
  name='hc-test-pg-'+runid+'-'+str(number)
  args=['docker','run','-d','--name',name,'--label','hc.audit='+LABEL,'--network','none',
        '--user','999:999','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
        '--memory','512m','--cpus','1','--pids-limit','128',
        '--tmpfs','/var/lib/postgresql/data:rw,nosuid,nodev,size=256m,uid=999,gid=999,mode=0700',
        '--tmpfs','/var/run/postgresql:rw,nosuid,nodev,size=8m,uid=999,gid=999',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=16m','--env','PGDATA=/var/lib/postgresql/data/db',
        '--env','POSTGRES_HOST_AUTH_METHOD=trust','--env','POSTGRES_USER=postgres',pgimage]
  command(args,stdout=subprocess.DEVNULL)
  try:
   for _ in range(60):
    # The image's temporary init server accepts Unix sockets before initdb
    # finishes. TCP becomes ready only on the final server.
    if subprocess.run(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
    time.sleep(.5)
   else:raise RuntimeError('Disposable PostgreSQL did not start')
   command(['docker','exec',name,'createdb','-h','127.0.0.1','-U','postgres',database])
   host='hc3536-postgres' if prefix=='HC3536' else '127.0.0.1'
   dsn='postgresql://postgres@'+host+':5432/'+database
   env={'MOWER_TEST_POSTGRES':'1','DATABASE_URL':dsn} if prefix=='MOWER' else {prefix+'_TEST_POSTGRES':'1',prefix+'_TEST_DATABASE_URL':dsn}
   args=base_run(source,network='container:'+name)
   if prefix=='HC3536':
    # Docker forbids --add-host with container network sharing. This test's
    # dedicated database hostname resolves only to its own loopback namespace.
    hosts=out/'postgres-hosts';hosts.write_text('127.0.0.1 localhost hc3536-postgres\n::1 localhost\n')
    args+=['--mount','type=bind,src='+str(hosts.resolve())+',dst=/etc/hosts,readonly']
   for key,value in env.items():args+=['--env',key+'='+value]
   args += [backend,'python','-B','/src/scripts/hc_test_suite.py','postgres','--module','tests.'+module]
   results[module]=execute(args,out/(module+'.log'))
   print(module,results[module]['ok'],flush=True)
  finally:
   details=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
   assert details['Config']['Labels'].get('hc.audit')==LABEL
   command(['docker','rm','-f',name],stdout=subprocess.DEVNULL)
 return {'ok':all(x['ok'] for x in results.values()),'modules':results}


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--profile',choices=('all',*PROFILES),default='all')
 parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--npm-cache',type=Path,help='Previously downloaded public npm cache; tests remain offline')
 parser.add_argument('--image-lock',type=Path,help='Explicit candidate container-name to image-ID map')
 args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
 if args.image_lock:
  values=json.loads(args.image_lock.read_text())
  if not isinstance(values,dict) or not all(isinstance(k,str) and re.fullmatch(r'sha256:[0-9a-f]{64}',v) for k,v in values.items()):
   raise ValueError('Invalid candidate image lock')
  IMAGE_OVERRIDES.update(values)
 if (out/'test-summary.json').exists():raise ValueError('Use a new evidence directory')
 runid=uuid.uuid4().hex[:12]
 sources={}
 for variant in ('standard','deployed'):
  sources[variant]=stage(Path('/tmp/hc-test-'+variant+'-'+runid),variant)
 backend=image('homecontrol-backend');pgimage=image('homecontrol-postgres')
 report={'ok':False,'started_at':datetime.now(timezone.utc).isoformat(),'production_changed':False,
         'network':'none; PostgreSQL clients share only their disposable DB namespace',
         'backend_image':backend,'postgres_image':pgimage,'profiles':{},
         'source_policies':{v:json.loads((s/'.hc-test-source.json').read_text()) for v,s in sources.items()}}
 try:
  for profile in PROFILES if args.profile=='all' else (args.profile,):
   source=sources['deployed' if profile in ('deployed','ownership','mdns') else 'standard']
   if profile=='postgres':
    result=postgres(source,backend,pgimage,out,runid)
   elif profile in ('unit','ownership','deployed','mdns'):
    selected=image('homecontrol-mdns') if profile=='mdns' else backend
    result=execute(base_run(source,root=profile=='ownership')+[selected,'python','-B','/src/scripts/hc_test_suite.py',profile],out/(profile+'.log'))
    result['image']=selected
   elif profile=='frontend':
    node=re.search(r'^FROM (node@sha256:[0-9a-f]+)',(ROOT/'infra/frontend/Dockerfile').read_text(),re.M)[1]
    # node_modules and build output exist only in the disposable tmpfs.
    if not args.npm_cache or not args.npm_cache.resolve().is_dir():
     raise ValueError('frontend requires --npm-cache; no networked fallback')
    cmd=base_run(source)+['--mount','type=bind,src='+str(args.npm_cache.resolve())+',dst=/cache,readonly',node,'sh','-c','cp -R /cache /tmp/npm-cache && cp -R /src/infra/frontend /tmp/frontend && cd /tmp/frontend && npm ci --offline --ignore-scripts --no-audit --no-fund --cache /tmp/npm-cache && node --test --test-reporter=tap tests/*.test.mjs && npm run build']
    result=execute(cmd,out/'frontend.log')
   else:
    folder={'bridges':'apps/bridge_runtime/tests','ingest':'apps/hc_ingest','x10':'apps/xiaomi-x10/tests'}[profile]
    selected=image({'bridges':'homecontrol-backend','ingest':'homecontrol-ingest','x10':'homecontrol-xiaomi-x10'}[profile])
    code='import sys,unittest,json;sys.path[:0]=["/src/apps/hc_ingest","/src/apps/bridge_runtime","/src/apps/xiaomi-x10","/src/infra/backend"];s=unittest.defaultTestLoader.discover("/src/'+folder+'",pattern="test_*.py");from hc_test_suite import flatten;ts=[t for t in flatten(s) if not t.__class__.__module__.endswith("_postgres")];r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ts));print(json.dumps(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped))));raise SystemExit(0 if r.wasSuccessful() and not r.skipped else 1)'
    result=execute(base_run(source)+['--env','PYTHONPATH=/src/scripts:/src/apps/bridge_runtime',selected,'python','-B','-c',code],out/(profile+'.log'))
   report['profiles'][profile]=result
   print(profile,result['ok'],flush=True)
  report['ok']=all(x['ok'] for x in report['profiles'].values())
 finally:
  report['finished_at']=datetime.now(timezone.utc).isoformat()
  (out/'test-summary.json').write_text(json.dumps(report,indent=2)+'\n')
  for source in sources.values():shutil.rmtree(source)
 return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
