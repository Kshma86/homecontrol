import json,subprocess,time,sys,tempfile,secrets
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-security-20261102-r18';S=K/'source';W=Path('/tmp/hc-access-combined-20261031');P=W/'private/pg-lab';P.mkdir(mode=0o700,exist_ok=True)
net='hc-combined-pg-20261031';db='hc3536-db';pool='hc3536-postgres';api='hc3536-handover-api';created=[];created_network=False
backend=json.loads((K/'release.json').read_text())['images']['backend']
pg=json.loads((K/'source/runtime.compose.json').read_text())['services']['postgres']['image']
poolimage=json.loads((K/'source/runtime.compose.json').read_text())['services']['pgbouncer']['image']
password=secrets.token_urlsafe(24)
def run(args,**kw):
 r=subprocess.run(args,capture_output=True,text=True,**kw)
 if r.returncode:
  (P/'error.log').write_text(r.stdout+r.stderr);raise RuntimeError('Private PG laboratory error log')
 return r

def sql(text):return run(['docker','exec','-i',db,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','hc3536','-d','hc3536_test'],input=text).stdout

def start(name,image,args,opts):
 assert subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0,'Unexpected existing lab container'
 run(['docker','run','-d','--name',name,*opts,image,*args]);created.append(name)

try:
 run(['docker','network','create','--internal',net]);created_network=True
 env=P/'postgres.env';env.write_text('POSTGRES_USER=hc3536\nPOSTGRES_DB=hc3536_test\nPOSTGRES_PASSWORD='+password+'\n');env.chmod(0o600)
 start(db,pg,[],['--network',net,'--tmpfs','/var/lib/postgresql/data:rw,size=192m','--env-file',str(env)])
 for _ in range(60):
  if subprocess.run(['docker','exec',db,'pg_isready','-U','hc3536','-d','hc3536_test'],capture_output=True).returncode==0:break
  time.sleep(.25)
 else:raise RuntimeError('Lab PG not ready')
 users=P/'users.txt';users.unlink(missing_ok=True);users.write_text('"hc3536" "'+password+'"\n');users.chmod(0o444)
 conf=P/'pool.ini';conf.unlink(missing_ok=True);conf.write_text('[databases]\nhc3536_test=host='+db+' port=5432 dbname=hc3536_test\n[pgbouncer]\nlisten_addr=0.0.0.0\nlisten_port=6432\nauth_type=scram-sha-256\nauth_file=/config/users.txt\npool_mode=transaction\nmax_client_conn=80\ndefault_pool_size=12\nignore_startup_parameters=extra_float_digits\n');conf.chmod(0o444)
 start(pool,poolimage,['/config/pool.ini'],['--network',net,'-v',str(conf)+':/config/pool.ini:ro','-v',str(users)+':/config/users.txt:ro','--entrypoint','pgbouncer'])
 testenv=P/'test.env';testenv.write_text('HC3536_TEST_POSTGRES=1\nHC3536_TEST_DATABASE_URL=postgresql://hc3536:'+password+'@hc3536-postgres:6432/hc3536_test\n');testenv.chmod(0o600)
 time.sleep(.5)
 r=subprocess.run(['docker','run','--rm','--network',net,'--read-only','--tmpfs','/tmp:rw,size=128m','--env-file',str(testenv),'-e','PYTHONPATH=/work/infra/backend','-e','PYTHONDONTWRITEBYTECODE=1','-v',str(S)+':/work:ro','-v',str(W/'run_pg.py')+':/runner.py:ro','-w','/work/infra/backend','--entrypoint','python',backend,'/runner.py'],capture_output=True,text=True)
 (W/'evidence/postgres-tests.log').write_text(r.stdout+r.stderr)
 assert r.returncode==0,'HC-35/36 transaction pooler tests failed'
 result=json.loads(r.stdout.strip().splitlines()[-1]);(W/'evidence/postgres-results.json').write_text(json.dumps(result,indent=2)+'\n')
 # A real stopped/running container exercises the handover guard without touching HC.
 run(['docker','create','--name',api,'--network','none','--read-only','--cap-drop','ALL','--entrypoint','python',backend,'-c','import time;time.sleep(120)']);created.append(api)
 sys.path.insert(0,str(B/'scripts/access_release'));from climate_handover import reconcile
 def mapped(args,**kwargs):
  args=list(args)
  if args[:4]==['docker','exec','-i','homecontrol-postgres']:args[3]=db
  elif args[-1]=='homecontrol-backend' and args[:2]==['docker','inspect']:args[-1]=api
  else:raise AssertionError('Unmapped production command in laboratory')
  return subprocess.run(args,**kwargs)
 seed="update hc.process_sensor_binding set entity_id=11 where process_key='climate_extra_fan_socket';update hc.power_wall_policy set auto_climate=(entity_id=11),auto_climate_on_at=case when entity_id=11 then now()+interval '5 minutes' else null end;"
 sql(seed)
 unchanged=sql("select json_build_object('binding',(select entity_id from hc.process_sensor_binding where process_key='climate_extra_fan_socket'),'flags',(select json_agg(json_build_array(entity_id,auto_climate) order by entity_id) from hc.power_wall_policy),'other_jobs',(select json_agg(row_to_json(x)) from hc.power_wall_schedule_session x));")
 journal=P/'receipts';journal.mkdir(exist_ok=True)
 run(['docker','start',api])
 try:reconcile(journal,'deploy',run=mapped)
 except RuntimeError:pass
 else:raise AssertionError('Running backend was allowed to reconcile')
 assert sql('select count(*) from hc.power_wall_policy where auto_climate_on_at is not null;').strip()=='1'
 run(['docker','stop','--timeout','3',api])
 deployed=reconcile(journal,'deploy',run=mapped);assert deployed['cancelled_entity_ids']==[11]
 assert sql('select count(*) from hc.power_wall_policy where auto_climate_on_at is not null;').strip()=='0'
 assert sql("select json_build_object('binding',(select entity_id from hc.process_sensor_binding where process_key='climate_extra_fan_socket'),'flags',(select json_agg(json_build_array(entity_id,auto_climate) order by entity_id) from hc.power_wall_policy),'other_jobs',(select json_agg(row_to_json(x)) from hc.power_wall_schedule_session x));")==unchanged
 sql('update hc.power_wall_policy set auto_climate_on_at=now() where entity_id=22;')
 rolled=reconcile(journal,'rollback',run=mapped);assert rolled['cancelled_entity_ids']==[22]
 assert sql('select count(*) from hc.power_wall_policy where auto_climate_on_at is not null;').strip()=='0'
 sql('update hc.power_wall_policy set auto_climate_on_at=now() where entity_id=11;')
 failed=P/'failed-receipts';failed.mkdir(exist_ok=True)
 def fail_transaction(args,**kwargs):
  if args[:2]==['docker','exec']:kwargs['input']=kwargs['input'].replace('COMMIT;','SELECT 1/0; COMMIT;')
  return mapped(args,**kwargs)
 try:reconcile(failed,'deploy',run=fail_transaction)
 except RuntimeError:pass
 else:raise AssertionError('Transaction failure was reported as success')
 assert not (failed/'deploy-climate-handover.json').exists()
 assert sql('select count(*) from hc.power_wall_policy where auto_climate_on_at is not null;').strip()=='1'
 result={'ok':True,'real_postgresql':True,'transaction_pooler_tests':19,'handover_scenarios':4,'running_backend_refused':True,'deploy_old_on_cancelled':True,'rollback_new_on_cancelled_no_replay':True,'binding_policy_flags_and_other_jobs_unchanged':True,'failed_transaction_rolled_back_no_success_receipt':True,'production_used':False,'published_ports':False}
 (W/'evidence/handover-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
 # Restore an actual custom-format dump into a fresh application-state database.
 dump=P/'application-state.dump'
 with dump.open('wb') as stream:
  subprocess.run(['docker','exec',db,'pg_dump','-U','hc3536','-d','hc3536_test','-Fc'],stdout=stream,stderr=subprocess.PIPE,check=True)
 sql('CREATE DATABASE hc3536_restored TEMPLATE template0;')
 with dump.open('rb') as stream:
  subprocess.run(['docker','exec','-i',db,'pg_restore','--exit-on-error','-U','hc3536','-d','hc3536_restored'],stdin=stream,capture_output=True,check=True)
 def restored(args,**kwargs):
  if args[:4]==['docker','exec','-i','homecontrol-postgres']:
   args=['docker','exec','-i','-e','POSTGRES_DB=hc3536_restored',db,*args[4:]]
   return subprocess.run(args,**kwargs)
  return mapped(args,**kwargs)
 restored_receipt=reconcile(journal,'restore',run=restored)
 assert restored_receipt['cancelled_entity_ids']==[11]
 env=P/'restored.env';env.write_text('DATABASE_URL=postgresql://hc3536:'+password+'@'+db+'/hc3536_restored\n');env.chmod(0o600)
 probe="""import os,json
from database_service import DatabaseService
from psycopg.rows import dict_row
from process_binding_service import ProcessBindingService
from power_wall_service import PowerWallService
from climate_fan_coordination import ClimateFanCoordinator
x=DatabaseService(os.environ['DATABASE_URL'])
c=ClimateFanCoordinator(lambda:x.conn(dict_row))
b=ProcessBindingService(x.fetch_all,x.fetch_one,x.execute_one,x.execute_sql,lambda t:str(t).strip(),lambda *a:None,lambda *a:None,climate_fan_coordinator=c);b._schema_ready=True
calls=[]
p=PowerWallService(x.fetch_all,x.fetch_one,x.execute_one,lambda *a:None,lambda:None,lambda *a:None,lambda *a:None,lambda *a:None,lambda t,default='':str(t or default),30,process_binding_entity_id=b.selected_entity_id,climate_fan_coordinator=c)
p.publish_switch=lambda row,target,source:(calls.append((row['entity_id'],target)) or (True,'fixture','test',{}))
assert b.binding('climate_extra_fan_socket')['configuration_state']=='valid'
assert b.selected_entity_id('climate_extra_fan_socket')==11
p.climate_delay_tick();assert not calls
assert x.fetch_one('select count(*) n from hc.power_wall_policy where auto_climate_on_at is not null')['n']==0
print(json.dumps({'ok':True,'real_pg_dump_restore':True,'candidate_binding_and_powerwall_modules':True,'selected_binding_preserved':True,'restored_old_on_cancelled_no_publish':True,'production_used':False}))
"""
 r=run(['docker','run','--rm','--network',net,'--env-file',str(env),'--read-only','--cap-drop','ALL','--entrypoint','python',backend,'-c',probe])
 report=json.loads(r.stdout);import hashlib
 report['dump_sha256']=hashlib.sha256(dump.read_bytes()).hexdigest()
 (W/'evidence/application-restore.json').write_text(json.dumps(report,indent=2)+'\n')
 result['handover_scenarios']=5;result['application_dump_restore']=True
 (W/'evidence/handover-results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(report))
finally:
 for name in reversed(created):subprocess.run(['docker','rm','-f',name],capture_output=True)
 if created_network:subprocess.run(['docker','network','rm',net],capture_output=True)
