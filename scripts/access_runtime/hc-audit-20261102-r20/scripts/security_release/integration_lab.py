"""Disposable real DB/pool/auth-MQTT and root IPC fixture. No production secrets."""
import json,os,secrets,subprocess,time,uuid
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-audit-20261102-r20';S=K/'source'
P=Path('/tmp')/('hc-r11-private-'+uuid.uuid4().hex);P.mkdir(mode=0o700)
N='hc-r11-lab-'+uuid.uuid4().hex[:8]+'-';created=[];volumes=[]
m=json.loads((K/'release.json').read_text());model=json.loads((S/'runtime.compose.json').read_text())
backend=m['images']['backend'];old=m['baseline']['homecontrol-backend']['image']
app_pass=secrets.token_urlsafe(32);reader_pass=secrets.token_urlsafe(32);bus_pass=secrets.token_urlsafe(32)
def run(args,**kw):
 r=subprocess.run(args,capture_output=True,text=True,timeout=120,**kw)
 if r.returncode:
  (P/'error.log').write_text(r.stdout+r.stderr);raise RuntimeError('Isolated integration failed: '+str(args[:3])+'; private '+str(P))
 return r.stdout

def start(name,image,args=(),options=()):
 full=N+name
 run(['docker','run','-d','--name',full,'--label','hc.audit=hc23-43-r17',*options,image,*args]);created.append(full);return full

def envfile(name,values):
 p=P/(name+'.env');p.write_text(''.join(k+'='+v+'\n' for k,v in values.items()));p.chmod(0o600);return p

def request(path):
 code='import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:5000'+path+'",timeout=3).read().decode())'
 return json.loads(run(['docker','exec',N+'backend','python','-c',code]))

def sql(statement):
 return run(['docker','exec','-i',N+'db','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','homecontrol','-p','55432','-d','homecontrol'],input=statement)

def stop_backend():
 run(['docker','stop','--time','10',N+'backend']);run(['docker','rm',N+'backend']);created.remove(N+'backend')
 # Exact release handover SQL after stopping the backend; no Docker host socket.
 import importlib.util
 spec=importlib.util.spec_from_file_location('handover',S/'scripts/access_release/climate_handover.py')
 import sys;sys.path.insert(0,str(S/'scripts/access_release'))
 h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 records=[json.loads(line) for line in sql(h.SQL).splitlines() if line.startswith('{')]
 assert len(records)==1

try:
 db=start('db',model['services']['postgres']['image'],['postgres','-p','55432','-c','shared_preload_libraries=pg_stat_statements'],['--network','none','--tmpfs','/var/lib/postgresql/data:rw,size=384m','-e','POSTGRES_USER=homecontrol','-e','POSTGRES_PASSWORD=disposable-r11-lab-only','-e','POSTGRES_DB=homecontrol'])
 for _ in range(100):
  if subprocess.run(['docker','exec',db,'pg_isready','-U','homecontrol','-p','55432'],capture_output=True).returncode==0:break
  time.sleep(.15)
 else:raise RuntimeError('Fixture database not ready')
 admin=envfile('admin',{'ADMIN':'postgresql://homecontrol:disposable-r11-lab-only@127.0.0.1:55432/homecontrol','APP':app_pass,'READER':reader_pass})
 init=P/'init.py';init.write_text('''import os,psycopg
from pathlib import Path
from migrate_hc38 import install
from migrate_hc07 import migrate
from migrate_hc39 import provision
with psycopg.connect(os.environ['ADMIN'],autocommit=True) as c:
 install(c,Path('/schema'),apply=True)
 migrate(c,Path('/schema'),apply=True,seed_initial=True)
 provision(c,Path('/schema'),apply=True,passwords={'hc_app':os.environ['APP'],'hc_lab':os.environ['READER']})
 c.execute(Path('/schema/062_hc33_ingest_sample_identity.sql').read_text(),prepare=False)
 c.execute("CREATE TABLE hc.f10_release_probe(value text); INSERT INTO hc.f10_release_probe VALUES ('preserved'); GRANT SELECT ON hc.f10_release_probe TO hc_app,hc_lab;")
print('Schema initialized')
''')
 run(['docker','run','--rm','--network','container:'+db,'--env-file',str(admin),'-v',str(S/'infra/db')+':/schema:ro','-v',str(init)+':/init.py:ro','-e','PYTHONPATH=/app','--entrypoint','python',backend,'/init.py'])
 for volume in ('ipc','state'):
  name=N+volume;run(['docker','volume','create',name]);volumes.append(name)
 run(['docker','run','--rm','--network','none','--user','0:0','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','FOWNER','-v',N+'ipc:/lab','-v',N+'state:/ai-state','--entrypoint','python',backend,'-c',
  'from pathlib import Path;import os;[(Path(p).mkdir(exist_ok=True),Path(p).chmod(m)) for p,m in [("/lab/backups",0o755),("/lab/ipc",0o755),("/lab/jobs",0o700)]];os.chown("/ai-state",10001,10001);Path("/ai-state").chmod(0o700);[(Path("/lab/backups/"+n).touch(),os.chown("/lab/backups/"+n,0,10001),Path("/lab/backups/"+n).chmod(0o660)) for n in ("ai-backup.lock","homecontrol-backup.lock")]'])
 password=P/'mqtt.password';password.write_text(bus_pass);password.chmod(0o444)
 passwd=P/'passwd';passwd.write_text(''.join(n+':'+bus_pass+'\n' for n in ('hc_backend','hc_ingest')));passwd.chmod(0o600)
 broker_image=model['services']['mqtt']['image']
 run(['docker','run','--rm','--network','none','--user',str(os.getuid())+':'+str(os.getgid()),'-v',str(P)+':/fixture','--entrypoint','mosquitto_passwd',broker_image,'-U','/fixture/passwd']);passwd.chmod(0o444)
 conf=P/'mosquitto.conf';conf.write_text('listener 1884 127.0.0.1\nallow_anonymous false\npassword_file /passwd\npersistence false\n');conf.chmod(0o444)
 start('mqtt',broker_image,['-c','/config'],['--network','container:'+db,'--user','1883:1883','--read-only','-v',str(conf)+':/config:ro','-v',str(passwd)+':/passwd:ro','--entrypoint','mosquitto'])
 pool=P/'pool.ini';users=P/'users.txt'
 users.write_text('"hc_app" "'+app_pass+'"\n');users.chmod(0o444)
 pool.write_text('[databases]\nhomecontrol=host=127.0.0.1 port=55432 dbname=homecontrol\nrestored=host=127.0.0.1 port=55432 dbname=restored\n[pgbouncer]\nlisten_addr=127.0.0.1\nlisten_port=5432\nauth_type=scram-sha-256\nauth_file=/config/users.txt\npool_mode=transaction\nmax_client_conn=100\ndefault_pool_size=12\nignore_startup_parameters=extra_float_digits\n');pool.chmod(0o444)
 start('pool',model['services']['pgbouncer']['image'],['/config/pool.ini'],['--network','container:'+db,'-v',str(pool)+':/config/pool.ini:ro','-v',str(users)+':/config/users.txt:ro','--entrypoint','pgbouncer'])
 fixture=P/'bin';fixture.mkdir()
 fake=fixture/'docker';fake.write_text('#!/usr/bin/env python3\nimport json,sys\na=sys.argv[1:]\nif a[0]=="ps":print(json.dumps(dict(ID="abcdef123456",Names="homecontrol-backend",Image="isolated",State="running",Status="Up")))\nelif a[0]=="version":print(json.dumps(dict(Version="isolated")))\nelse:raise SystemExit(1)\n');fake.chmod(0o755)
 hostenv=envfile('host',{'HC_BACKUP_DIR':'/lab/backups','HC_AI_STATE_DIR':'/ai-state','PATH':'/fixture:/usr/local/bin:/usr/bin:/bin'})
 start('host',backend,['/source/scripts/hostops/server.py','--socket','/lab/ipc/operations.sock','--journal','/lab/jobs'],['--network','container:'+db,'--user','0:0','--read-only','--tmpfs','/tmp:rw,size=32m','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','FOWNER','--cap-add','DAC_OVERRIDE','--env-file',str(hostenv),'-v',str(S)+':/source:ro','-v',str(fixture)+':/fixture:ro','-v',N+'ipc:/lab','-v',N+'state:/ai-state','--entrypoint','python'])
 baseenv={'DATABASE_URL':'postgresql://hc_app:'+app_pass+'@127.0.0.1:5432/homecontrol','SQL_LAB_DATABASE_URL':'postgresql://hc_lab:'+reader_pass+'@127.0.0.1:55432/homecontrol','MQTT_HOST':'127.0.0.1','MQTT_PORT':'1884','MQTT_USERNAME':'hc_backend','MQTT_PASSWORD_FILE':'/secret','MQTT_AUTH_REQUIRED':'1','HC_HOST_OPS_SOCKET':'/lab/ipc/operations.sock','HC_BACKUP_DIR':'/lab/backups','HC_AI_STATE_DIR':'/ai-state','HOME':'/tmp'}
 stages=[]
 for index,(label,image) in enumerate((('previous',old),('candidate',backend),('rollback',old),('restored_candidate',backend))):
  env=baseenv.copy()
  if label=='restored_candidate':
   dump=subprocess.run(['docker','exec',db,'pg_dump','-Fc','-U','homecontrol','-p','55432','homecontrol'],capture_output=True,check=True).stdout
   run(['docker','exec',db,'createdb','-U','homecontrol','-p','55432','restored'])
   restored=subprocess.run(['docker','exec','-i',db,'pg_restore','--exit-on-error','-U','homecontrol','-p','55432','-d','restored'],input=dump,capture_output=True)
   if restored.returncode:(P/'restore.log').write_bytes(restored.stderr);raise RuntimeError('DB restore failed')
   env={k:v.replace('/homecontrol','/restored') if k in ('DATABASE_URL','SQL_LAB_DATABASE_URL') else v for k,v in env.items()}
  api_env=envfile('backend-'+str(index),env)
  start('backend',image,options=['--network','container:'+db,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=128m','--env-file',str(api_env),'-v',N+'ipc:/lab','-v',N+'state:/ai-state','-v',N+'state:/srv/docker/homecontrol/infra/private','-v',str(password)+':/secret:ro','-v',str(S/'infra/db')+':/srv/docker/homecontrol/infra/db:ro','-v',str(S/'docs')+':/srv/docker/homecontrol/docs:ro'])
  endpoint='/health/ready' if image==backend else '/health'
  for _ in range(120):
   try:
    health=request(endpoint)
    if health.get('ok'):break
   except Exception:pass
   time.sleep(.5)
  else:raise RuntimeError('Backend readiness failed: '+label)
  probe='''import os,psycopg
from host_operations_client import HostOperationsClient
assert os.geteuid()==10001
assert HostOperationsClient().call('containers',timeout=5)
with psycopg.connect(os.environ['DATABASE_URL']) as c:assert c.execute('select value from hc.f10_release_probe').fetchone()[0]=='preserved'
print('ok')'''
  assert run(['docker','exec',N+'backend','python','-c',probe]).strip()=='ok'
  stages.append({'stage':label,'ready':True,'root_ipc':True,'data_preserved':True})
  if index<3:stop_backend()
 ingest_env=envfile('ingest',{'PG_HOST':'127.0.0.1','PG_PORT':'5432','PG_DB':'restored','PG_USER':'hc_app','PG_PASSWORD':app_pass,'MQTT_HOST':'127.0.0.1','MQTT_PORT':'1884','MQTT_USERNAME':'hc_ingest','MQTT_PASSWORD_FILE':'/secret','MQTT_AUTH_REQUIRED':'1','HEARTBEAT_WRITE_INTERVAL_SECONDS':'1'})
 start('ingest',m['images']['hc_ingest'],options=['--network','container:'+db,'--read-only','--tmpfs','/tmp:rw,size=32m','--env-file',str(ingest_env),'-v',str(password)+':/secret:ro'])
 for _ in range(60):
  try:
   status=json.loads(run(['docker','exec',N+'ingest','python','-c','from pathlib import Path;print(Path("/tmp/hc_ingest_status.json").read_text())']))
   if status.get('mqtt_connected') and status.get('db_ready') is True:break
  except Exception:pass
  time.sleep(.25)
 else:raise RuntimeError('Ingest not ready')
 result={'ok':True,'real_postgres':True,'real_pgbouncer':True,'authenticated_mqtt':True,'generated_fixture_credentials_only':True,'stages':stages,'candidate_ingest_ready':True,'real_db_dump_restore':True,'fan_handover_sql':True,'hostops_named_capability':True,'production_access':False,'network':'none with shared namespace; no host ports','private_log_directory':str(P)}
 (K/'evidence/integration.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 for name in reversed(created):
  logs=subprocess.run(['docker','logs','--tail','120',name],capture_output=True)
  (P/(name+'.log')).write_bytes(logs.stdout+logs.stderr)
  subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for name in volumes:subprocess.run(['docker','volume','rm',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
