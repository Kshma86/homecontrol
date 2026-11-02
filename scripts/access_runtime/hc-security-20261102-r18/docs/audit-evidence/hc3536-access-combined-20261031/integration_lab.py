import json,os,secrets,shutil,subprocess,time
from pathlib import Path
B=Path('/srv/docker/homecontrol');E=Path('/tmp/hc-access-combined-20261031');K=B/'backups/releases/hc-security-20261102-r18';S=K/'source'
P=E/'integration-private';P.mkdir(mode=0o700,exist_ok=True)
N='hc-combined-r10-lab-';created=[];volumes=[]
manifest=json.loads((K/'release.json').read_text());backend=manifest['images']['backend'];ingest=manifest['images']['hc_ingest']
app_pass=secrets.token_urlsafe(32);reader_pass=secrets.token_urlsafe(32)

def run(args,**kw):
 r=subprocess.run(args,capture_output=True,text=True,**kw)
 if r.returncode:
  (E/'integration-error.log').write_text(r.stdout+r.stderr);raise RuntimeError('Isolated integration failed; private integration-error.log')
 return r.stdout

def start(name,image,args=(),options=()):
 full=N+name
 run(['docker','run','-d','--name',full,*options,image,*args]);created.append(full);return full

def envfile(name,values):
 p=P/(name+'.env');p.write_text(''.join(k+'='+v+'\n' for k,v in values.items()));p.chmod(0o600);return p

def request(path):
 code='import json,urllib.request;print(urllib.request.urlopen("http://127.0.0.1:5000'+path+'",timeout=3).read().decode())'
 return json.loads(run(['docker','exec',N+'backend','python','-c',code]))

try:
 db=start('db','postgres:16',['postgres','-p','55432','-c','shared_preload_libraries=pg_stat_statements'],['--network','none','--tmpfs','/var/lib/postgresql/data:rw,size=256m','-e','POSTGRES_USER=homecontrol','-e','POSTGRES_PASSWORD=disposable-access-lab-only','-e','POSTGRES_DB=homecontrol'])
 for _ in range(50):
  if subprocess.run(['docker','exec',db,'pg_isready','-U','homecontrol','-p','55432'],capture_output=True).returncode==0:break
  time.sleep(.1)
 else:raise RuntimeError('Fixture database not ready')
 admin=envfile('admin',{'ADMIN':'postgresql://homecontrol:disposable-access-lab-only@127.0.0.1:55432/homecontrol','APP':app_pass,'READER':reader_pass})
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
print('Isolated baseline/059/060/061/062 initialized')
''')
 run(['docker','run','--rm','--network','container:'+db,'--env-file',str(admin),'-v',str(S/'infra/db')+':/schema:ro','-v',str(init)+':/init.py:ro','-e','PYTHONPATH=/app','--entrypoint','python',backend,'/init.py'])
 # Root-owned local volumes isolate the privileged executor from the API.
 for volume in ('ipc','state','broker'):
  name=N+volume;run(['docker','volume','create',name]);volumes.append(name)
 run(['docker','run','--rm','--network','none','--user','0:0','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','FOWNER','-v',N+'ipc:/lab','-v',N+'state:/ai-state','--entrypoint','python',backend,'-c',
  'from pathlib import Path;import os;[(Path(p).mkdir(exist_ok=True),Path(p).chmod(m)) for p,m in [("/lab/backups",0o755),("/lab/ipc",0o755),("/lab/jobs",0o700)]];os.chown("/ai-state",10001,10001);Path("/ai-state").chmod(0o700);[(Path("/lab/backups/"+n).touch(),os.chown("/lab/backups/"+n,0,10001),Path("/lab/backups/"+n).chmod(0o660)) for n in ("ai-backup.lock","homecontrol-backup.lock")]'])
 # Exercise production UID 1883 and 0600 broker credentials on an isolated volume.
 run(['docker','run','--rm','--network','none','--user','0:0','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','FOWNER','-v',N+'broker:/broker','-v',str(K/'private/runtime/mqtt/broker')+':/seed:ro','--entrypoint','python',backend,'-c',
  'from pathlib import Path;import os,shutil;[(shutil.copyfile(p,Path("/broker")/p.name),os.chmod(Path("/broker")/p.name,0o600),os.chown(Path("/broker")/p.name,1883,1883)) for p in Path("/seed").iterdir()];os.chmod("/broker",0o700);os.chown("/broker",1883,1883)'])
 # Same authenticated broker configuration and credentials, but disposable storage.
 broker=start('mqtt','sha256:077fe4ff4c49df1e860c98335c77dda08360629e0e2a718147027e4db3eace9d',['-c','/mosquitto/config/mosquitto.conf'],['--network','container:'+db,'--user','1883:1883','--read-only','--tmpfs','/mosquitto/data:rw,uid=1883,gid=1883,mode=0700','-v',N+'broker:/mosquitto/config:ro','--entrypoint','mosquitto'])
 pool=P/'pool.ini';users=P/'users.txt'
 users.unlink(missing_ok=True);pool.unlink(missing_ok=True)
 users.write_text('"hc_app" "'+app_pass+'"\n');users.chmod(0o444)
 pool.write_text('[databases]\nhomecontrol=host=127.0.0.1 port=55432 dbname=homecontrol\n[pgbouncer]\nlisten_addr=127.0.0.1\nlisten_port=5432\nauth_type=scram-sha-256\nauth_file=/config/users.txt\npool_mode=transaction\nmax_client_conn=60\ndefault_pool_size=8\nignore_startup_parameters=extra_float_digits\n');pool.chmod(0o444)
 start('pool','edoburu/pgbouncer:1.22.1-p0',['/config/pool.ini'],['--network','container:'+db,'-v',str(pool)+':/config/pool.ini:ro','-v',str(users)+':/config/users.txt:ro','--entrypoint','pgbouncer'])
 fixture=P/'bin';fixture.mkdir(exist_ok=True)
 fake=fixture/'docker';fake.write_text('#!/usr/bin/env python3\nimport json,sys\na=sys.argv[1:]\nif a[0]=="ps":print(json.dumps(dict(ID="abcdef123456",Names="homecontrol-backend",Image="isolated",State="running",Status="Up")))\nelif a[0]=="version":print(json.dumps(dict(Version="isolated")))\nelif a[0]=="restart":print("abcdef123456")\nelse:raise SystemExit(1)\n');fake.chmod(0o755)
 hostenv=envfile('host',{'HC_BACKUP_DIR':'/lab/backups','HC_AI_STATE_DIR':'/ai-state','PATH':'/fixture:/usr/local/bin:/usr/bin:/bin'})
 start('host',backend,['/source/scripts/hostops/server.py','--socket','/lab/ipc/operations.sock','--journal','/lab/jobs'],['--network','container:'+db,'--user','0:0','--read-only','--tmpfs','/tmp:rw,size=32m','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','FOWNER','--cap-add','DAC_OVERRIDE','--env-file',str(hostenv),'-v',str(S)+':/source:ro','-v',str(fixture)+':/fixture:ro','-v',N+'ipc:/lab','-v',N+'state:/ai-state','--entrypoint','python'])
 api_env=envfile('backend',{'DATABASE_URL':'postgresql://hc_app:'+app_pass+'@127.0.0.1:5432/homecontrol','SQL_LAB_DATABASE_URL':'postgresql://hc_lab:'+reader_pass+'@127.0.0.1:55432/homecontrol',
  'MQTT_HOST':'127.0.0.1','MQTT_PORT':'1884','MQTT_USERNAME':'hc_backend','MQTT_PASSWORD_FILE':'/secret','MQTT_AUTH_REQUIRED':'1','HC_HOST_OPS_SOCKET':'/lab/ipc/operations.sock','HC_BACKUP_DIR':'/lab/backups','HC_AI_STATE_DIR':'/ai-state','HC_ENABLE_SAFETY_WORKER':'0','HC_CONTEXT_REFRESH_ENABLED':'0','HOME':'/tmp'})
 start('backend',backend,options=['--network','container:'+db,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=128m','--env-file',str(api_env),'-v',N+'ipc:/lab','-v',N+'state:/ai-state','-v',N+'state:/srv/docker/homecontrol/infra/private','-v',str(K/'private/runtime/mqtt/credentials/backend.password')+':/secret:ro','-v',str(S/'infra/db')+':/srv/docker/homecontrol/infra/db:ro','-v',str(S/'docs')+':/srv/docker/homecontrol/docs:ro'])
 health=None
 for _ in range(75):
  try:
   health=request('/health')
   if health.get('db_ok') and health.get('mqtt_ok'):break
  except Exception:pass
  time.sleep(.2)
 else:raise RuntimeError('Candidate backend did not become ready')
 # Candidate ingest connects with its own identity, using the restricted DB role.
 ingest_env=envfile('ingest',{'PG_HOST':'127.0.0.1','PG_PORT':'5432','PG_DB':'homecontrol','PG_USER':'hc_app','PG_PASSWORD':app_pass,
  'MQTT_HOST':'127.0.0.1','MQTT_PORT':'1884','MQTT_USERNAME':'hc_ingest','MQTT_PASSWORD_FILE':'/secret','MQTT_AUTH_REQUIRED':'1','HEARTBEAT_WRITE_INTERVAL_SECONDS':'1'})
 start('ingest',ingest,options=['--network','container:'+db,'--read-only','--tmpfs','/tmp:rw,size=32m','--env-file',str(ingest_env),'-v',str(K/'private/runtime/mqtt/credentials/ingest.password')+':/secret:ro'])
 ingest_status=None
 for _ in range(40):
  try:
   ingest_status=json.loads(run(['docker','exec',N+'ingest','python','-c','from pathlib import Path;print(Path("/tmp/hc_ingest_status.json").read_text())']))
   if ingest_status.get('mqtt_connected') and ingest_status.get('db_ready') is True:break
  except Exception:pass
  time.sleep(.2)
 else:raise RuntimeError('Candidate ingest did not become ready')
 # Verify actual root socket ownership and the non-root service's capability path.
 probe='''import os,json,stat
from pathlib import Path
from host_operations_client import HostOperationsClient,HostBackupService
from scoped_ai_power_coordination import ScopedAiPowerCoordinator
assert os.geteuid()==10001
p=Path('/lab/ipc/operations.sock');s=p.stat();assert s.st_uid==0 and s.st_gid==10001 and stat.S_IMODE(s.st_mode)==0o660
assert not Path('/var/run/docker.sock').exists()
c=HostOperationsClient();assert c.call('containers')[0]['Names']==['/homecontrol-backend']
try:c.call('exec',command=['id'])
except ValueError:pass
else:raise AssertionError('general command accepted')
proxy=HostBackupService(c);result,status=proxy.create_payload(lambda *a:{});assert status==202
with ScopedAiPowerCoordinator('/lab/backups').locked() as state:assert state['version']==1
for name in ('/app/app.py','/lab/backups/forged.tar.gz'):
 try:Path(name).write_text('not allowed')
 except OSError:pass
 else:raise AssertionError('protected write succeeded')
print(json.dumps(dict(uid=10001,socket_root_10001_0660=True,root_rpc_allowed=True,backup_queued=True,ai_state_shared=True,no_docker_socket=True,protected_writes_denied=True)))
'''
 root_result=json.loads(run(['docker','exec',N+'backend','python','-c',probe]))
 deny=run(['docker','run','--rm','--network','none','--user','10002:10001','-e','HC_HOST_OPS_SOCKET=/lab/ipc/operations.sock','-v',N+'ipc:/lab:ro','--entrypoint','python',backend,'-c','from host_operations_client import HostOperationsClient;\ntry: HostOperationsClient().call("containers")\nexcept Exception: print("denied")\nelse: raise SystemExit(2)']).strip()
 assert deny=='denied'
 result=dict(ok=True,production_used=False,published_ports=False,network='none; shared isolated namespace',
  broker_uid_1883_private_0600_config=True,real_postgresql=True,real_pgbouncer=True,authenticated_mqtt=True,candidate_ingest_mqtt_and_db_ready=True,nonroot_candidate_backend_ready=True,
  host_executor_uid=0,host_executor_docker='strict fake CLI fixture; no daemon socket',wrong_peer_uid_denied=True,**root_result)
 (E/'integration-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 for name in reversed(created):
  logs=subprocess.run(['docker','logs','--tail','100',name],capture_output=True,text=True)
  (E/(name+'.log')).write_text(logs.stdout+logs.stderr)
  subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for name in volumes:subprocess.run(['docker','volume','rm',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
