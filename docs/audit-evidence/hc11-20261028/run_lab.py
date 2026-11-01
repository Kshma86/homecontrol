import json,subprocess,time,pathlib,os
ROOT=pathlib.Path('/srv/docker/homecontrol');E=pathlib.Path('/tmp/hc11-20261028');E.mkdir(parents=True,exist_ok=True);E.chmod(0o777)
def run(*args,**kw):return subprocess.run(['docker',*args],check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
names=['hc11-lab-test','hc11-lab-db','hc11-lab-mqtt'];volume='hc11-lab-data'
(E/'mosquitto.conf').write_text('listener 1883 127.0.0.1\nallow_anonymous true\npersistence false\n');(E/'mosquitto.conf').chmod(0o644)
for marker in E.glob('*-stop'):marker.unlink()
for marker in E.glob('*-start'):marker.unlink()
try:
 run('volume','create',volume)
 run('run','--rm','--network','none','--user','0','--cap-drop','ALL','--cap-add','CHOWN','-v',volume+':/data','--entrypoint','chown','postgres:16','999:999','/data')
 run('run','-d','--name',names[2],'--network','none','--cap-drop','ALL','--user','1883:1883','--read-only','-v',str(E/'mosquitto.conf')+':/mosquitto/config/mosquitto.conf:ro','eclipse-mosquitto:2')
 run('run','-d','--name',names[1],'--network','container:'+names[2],'--user','999:999','--cap-drop','ALL','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=hc11_recovery_test','-v',volume+':/var/lib/postgresql/data','postgres:16')
 for i in range(100):
  r=subprocess.run(['docker','exec',names[1],'pg_isready','-h','127.0.0.1','-U','postgres','-d','hc11_recovery_test'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  if r.returncode==0:break
  time.sleep(.1)
 else:raise RuntimeError('lab PG readiness')
 logfile=(E/'postgres-integration.log').open('w')
 command=['docker','run','--rm','--name',names[0],'--network','container:'+names[2],'--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=64m','-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/audit/apps/hc_ingest','-e','HC11_RECOVERY_LAB=1','-v',str(ROOT)+':/audit:ro','-v',str(E)+':/evidence','--workdir','/audit/apps/hc_ingest','--entrypoint','python','homecontrol-ingest:hc-refactor-20261026-r4','-m','unittest','-v','test_ingest_recovery_postgres']
 p=subprocess.Popen(command,stdout=logfile,stderr=subprocess.STDOUT)
 deadline=time.monotonic()+90
 while p.poll() is None:
  for action in ('stop','start'):
   marker=E/('request-'+action)
   if marker.exists():
    marker.unlink();run(action,names[1]);(E/('done-'+action)).touch()
  if time.monotonic()>deadline:p.terminate();raise RuntimeError('lab timeout')
  time.sleep(.05)
 if p.returncode:raise RuntimeError('integration failed; see postgres-integration.log')
finally:
 for name in names:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subprocess.run(['docker','volume','rm',volume],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
