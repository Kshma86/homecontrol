#!/usr/bin/env python3
"""Candidate/rollback rehearsal on the explicitly isolated laboratory only."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parents[1]
RELEASE=BASE/'backups/releases/hc-refactor-20261026-r4'
DB='hc-f1-f6a-repair-db'
DATABASE='hc_f6_restore_source'
PREFIX='hc-refactor-lab-'
VOLUME_PREFIX='hc-f1-f6a-'
EVIDENCE=Path('/tmp/hc-f1-f6a-repair')


def run(args,**kwargs):
    result=subprocess.run(args,capture_output=True,text=True,**kwargs)
    if result.returncode:
        (EVIDENCE/'lab-command-error.log').write_text(result.stdout+result.stderr)
        raise RuntimeError('Laboratory command failed; see private lab-command-error.log')
    return result.stdout


def inspect(name): return json.loads(run(['docker','inspect',name]))[0]


def sql(statement,database=DATABASE):
    return run(['docker','exec','-i',DB,'psql','-X','-U','homecontrol','-d',database,'-At','-v','ON_ERROR_STOP=1'],input=statement)


def policies():
    result={}
    for table in ('irrigation_pilot_config','irrigation_solar_pump_config','scheduler_config',
                  'domain_season_profile','domain_season_active','combustion_safety_config','process_sensor_binding','power_wall_policy'):
        fields=['updated_at','last_action_at','last_action','last_error','auto_climate_on_at']
        if table=='irrigation_solar_pump_config':fields.append('latest_decision')
        excluded='array['+','.join("'"+field+"'" for field in fields)+']'
        value='(to_jsonb(t)-'+excluded+')::text'
        result[table]=sql("select md5(coalesce(string_agg("+value+",'' order by "+value+"),'')) from hc."+table+" t").strip()
    return result


def http(path,method='GET',body=None,port=5000):
    code='''import json,sys,urllib.request,urllib.error
path,method,body,port=sys.argv[1:]
r=urllib.request.Request('http://127.0.0.1:'+port+path,data=None if body=='null' else body.encode(),method=method,headers={'Content-Type':'application/json'})
try:
 response=urllib.request.urlopen(r,timeout=4);code=response.status;data=response.read().decode()
except urllib.error.HTTPError as e:code=e.code;data=e.read().decode()
try:data=json.loads(data)
except ValueError:data={'html':bool(data)}
print(json.dumps({'status':code,'body':data}))
'''
    return json.loads(run(['docker','exec',PREFIX+'backend','python','-c',code,path,method,json.dumps(body),str(port)]))


def container(name,image,args=(),env_file=None,mounts=(),user='1000:1000',entrypoint=None):
    command=['docker','run','-d','--pull','never','--name',PREFIX+name,'--network','container:'+DB,
             '--read-only','--user',user,'--cap-drop','ALL','--security-opt','no-new-privileges',
             '--memory','1g','--tmpfs','/tmp:rw,size=128m']
    if env_file:command+=['--env-file',str(env_file)]
    for source,target in mounts:command+=['-v',str(source)+':'+target]
    if entrypoint:command+=['--entrypoint',entrypoint]
    run(command+[image,*args])


def stop(name):
    result=subprocess.run(['docker','inspect',PREFIX+name],capture_output=True)
    if result.returncode==0:run(['docker','rm','-f',PREFIX+name])


def main(*, after_phase=None):
    manifest=json.loads((RELEASE/'release.json').read_text())
    row=inspect(DB)
    if row['HostConfig']['NetworkMode']!='none' or row['NetworkSettings']['Ports']:
        raise RuntimeError('Database must have no network or published ports')
    if not all(m['Name'].startswith(VOLUME_PREFIX) for m in row['Mounts'] if m['Type']=='volume'):
        raise RuntimeError('Database volume is outside this laboratory')
    EVIDENCE.mkdir(mode=0o700,exist_ok=True)
    run(['docker','exec',DB,'sh','-c','printf "\\n127.0.0.1 backend\\n" >> /etc/hosts'])
    before=policies()
    (EVIDENCE/'operator-policy-before.json').write_text(json.dumps(before,indent=2)+'\n')
    baseline_count=int(sql('select count(*) from hc.measurement'))
    private=EVIDENCE/'lab-private';private.mkdir(mode=0o700,exist_ok=True)
    app_password=secrets.token_urlsafe(36);reader_password=secrets.token_urlsafe(36);admin_password=secrets.token_urlsafe(36)
    sys.path.insert(0,str(BASE/'scripts'))
    from restore_runtime import roles
    def target_runner(args,**kwargs):
        if args[:4]!=['docker','exec','-i','homecontrol-postgres']:raise RuntimeError('Unexpected role command')
        return subprocess.run([*args[:3],DB,*args[4:]],**kwargs)
    roles({'HC_APP_DB_PASSWORD':app_password,'HC_LAB_DB_PASSWORD':reader_password},run=target_runner)
    sql("alter role homecontrol password '"+admin_password+"';",database='postgres')
    run(['docker','exec','--user','postgres',DB,'sh','-c',
         'printf "local all all trust\\nhost all all 127.0.0.1/32 scram-sha-256\\nhost all all ::1/128 scram-sha-256\\n" > "$PGDATA/pg_hba.conf"; pg_ctl reload -D "$PGDATA"'])
    def env_file(name,values):
        path=private/name
        path.write_text(''.join(key+'='+str(value)+'\n' for key,value in values.items()));path.chmod(0o600)
        return path
    migration=env_file('migration.env',{'HC_RESTORE_ADMIN_DATABASE_URL':'postgresql://homecontrol:'+admin_password+'@127.0.0.1:5432/'+DATABASE,
                        'HC_APP_DB_PASSWORD':app_password,'HC_LAB_DB_PASSWORD':reader_password})
    command=['docker','run','--rm','--pull','never','--network','container:'+DB,'--read-only','--user','1000:1000',
             '--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=64m','--env-file',str(migration),
             '-v',str(RELEASE/'source/infra/db')+':/srv/docker/homecontrol/infra/db:ro','--entrypoint','python',
             manifest['images']['backend'],'/app/restore_runtime_schema.py']
    run(command);run(command)  # explicit migration repeatability
    if policies()!=before:raise RuntimeError('Migration changed an operator policy')
    if int(sql('select count(*) from hc.measurement'))!=baseline_count:raise RuntimeError('Migration changed measurement rows')
    pool=private/'pgbouncer.ini'
    pool.write_text('[databases]\n'+DATABASE+' = host=127.0.0.1 port=5432 dbname='+DATABASE+' user=hc_app password='+app_password+'\n[pgbouncer]\nlisten_addr=127.0.0.1\nlisten_port=6432\nauth_type=plain\nauth_file=/config/userlist.txt\npool_mode=transaction\nmax_client_conn=100\ndefault_pool_size=16\nignore_startup_parameters=extra_float_digits,options\npidfile=/tmp/pgbouncer.pid\n')
    users=private/'userlist.txt';users.write_text('"hc_app" "'+app_password+'"\n')
    broker=private/'mosquitto.conf';broker.write_text('listener 1883 127.0.0.1\nallow_anonymous true\npersistence false\nlog_type error\n')
    for path in (pool,users,broker):path.chmod(0o600)
    backups=EVIDENCE/'lab-backups';backups.mkdir(mode=0o700,exist_ok=True)
    staging=EVIDENCE/'lab-staging';staging.mkdir(mode=0o700,exist_ok=True)
    backend_env=env_file('backend.env',{'DATABASE_URL':'postgresql://hc_app:'+app_password+'@127.0.0.1:6432/'+DATABASE,
        'SQL_LAB_DATABASE_URL':'postgresql://hc_lab:'+reader_password+'@127.0.0.1:5432/'+DATABASE,
        'MQTT_HOST':'127.0.0.1','MQTT_PORT':1883,'HC_ENABLE_SAFETY_WORKER':0,'HC_BACKUP_DIR':'/lab/backups',
        'HC_RESTORE_STAGING_DIR':'/lab/staging','AI_NODE_HOST':'','AI_NODE_MAC':'','OPENWEATHER_API_KEY':'',
        'MOWER_REMOTE_URL':'http://127.0.0.1:9','AI_SERVER_URL':'http://127.0.0.1:9'})
    ingest_env=env_file('ingest.env',{'MQTT_HOST':'127.0.0.1','MQTT_PORT':1883,'PG_HOST':'127.0.0.1','PG_PORT':6432,
                                    'PG_DB':DATABASE,'PG_USER':'hc_app','PG_PASSWORD':app_password})
    phases=[]
    try:
        for name in ('backend','ingest','frontend','broker','pool'):stop(name)
        container('pool','edoburu/pgbouncer:1.22.1-p0',args=('/config/pgbouncer.ini',),entrypoint='pgbouncer',mounts=((pool,'/config/pgbouncer.ini:ro'),(users,'/config/userlist.txt:ro')))
        container('broker','eclipse-mosquitto:2',args=('-c','/config/mosquitto.conf'),entrypoint='mosquitto',mounts=((broker,'/config/mosquitto.conf:ro'),))
        for phase in ('release','rollback','release-again'):
            for name in ('backend','ingest','frontend'):stop(name)
            rollback=phase=='rollback'
            backend_image=manifest['rollback_image'] if rollback else manifest['images']['backend']
            ingest_image=manifest['previous_ingest'] if rollback else manifest['images']['ingest']
            frontend_image=manifest['previous_frontend'] if rollback else manifest['images']['frontend']
            container('backend',backend_image,env_file=backend_env,mounts=((backups,'/lab/backups'),(staging,'/lab/staging'),(RELEASE/'source/scripts','/srv/docker/homecontrol/scripts:ro')))
            container('ingest',ingest_image,env_file=ingest_env)
            # Nginx runs as an ordinary user; writable cache/pid only in tmpfs.
            run(['docker','run','-d','--pull','never','--name',PREFIX+'frontend','--network','container:'+DB,
                 '--read-only','--user','101:101','--cap-drop','ALL','--security-opt','no-new-privileges',
                 '--tmpfs','/tmp:rw,size=16m','--tmpfs','/run:rw,mode=1777,size=8m','--tmpfs','/var/cache/nginx:rw,mode=1777,size=16m',
                 '--entrypoint','nginx',frontend_image,'-g','daemon off;'])
            health=None
            for attempt in range(60):
                try:
                    health=http('/health')
                    if health['status']==200 and health['body'].get('db_ok') and health['body'].get('mqtt_ok'):break
                except Exception:pass
                time.sleep(1)
            else:raise RuntimeError('Backend health did not become ready: '+phase)
            schema=http('/api/sql-lab/schema')
            if schema['status']!=(503 if rollback else 200):raise RuntimeError('SQL Lab protection differs: '+phase)
            if rollback:
                for path,method,body in (('/api/sql-lab/query','POST',{'sql':'select 1'}),('/api/sql-lab/preview','GET',None),('/api/ai/node/command','POST',{'command':'shutdown'}),('/api/backup/create','POST',{})):
                    if http(path,method,body)['status']!=503:raise RuntimeError('Restricted rollback allowed an incompatible action')
            front=http('/',port=3000)
            if front['status']!=200:raise RuntimeError('Frontend unavailable')
            heartbeat=float(run(['docker','exec',PREFIX+'ingest','python','-c','import os,time;print(time.time()-os.stat("/tmp/hc_ingest_heartbeat").st_mtime)']).strip())
            if heartbeat>30:raise RuntimeError('Ingest heartbeat is stale')
            current=policies()
            (EVIDENCE/('operator-policy-'+phase+'.json')).write_text(json.dumps(current,indent=2)+'\n')
            if current!=before:raise RuntimeError('Runtime changed operator policy: '+phase)
            if after_phase:after_phase(phase)
            phases.append(dict(phase=phase,health=health['body'],sql_lab_status=schema['status'],frontend_status=front['status'],ingest_heartbeat_age=round(heartbeat,2),operator_policy_unchanged=True))
            print('Isolated phase passed: '+phase,flush=True)
        result=dict(ok=True,phases=phases,full_owner_acl_restore=True,measurement_rows=baseline_count,
                    explicit_migrations_repeated=True,physical_commands=False,production_changed=False,
                    rollback_restrictions=['SQL Lab','backup mutations','AI power commands'],real_systemd_manager=False)
        (EVIDENCE/'cutover-rollback-results.json').write_text(json.dumps(result,indent=2)+'\n')
    finally:
        for name in ('backend','ingest','frontend','pool','broker'):
            try:
                log=subprocess.run(['docker','logs',PREFIX+name],capture_output=True,text=True);(EVIDENCE/('lab-'+name+'.log')).write_text(log.stdout+log.stderr)
            except Exception:pass
            stop(name)


if __name__=='__main__':main()
