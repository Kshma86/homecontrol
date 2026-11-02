#!/usr/bin/env python3
"""r18: guarded platform/HA cutover using the reviewed router transaction."""
import argparse
import importlib.util
import json,os
from pathlib import Path
import shutil,signal,subprocess,sys,time,urllib.request,uuid

sys.dont_write_bytecode=True
BASE=Path('/srv/docker/homecontrol')
NAME='hc-audit-20261102-r20'
KIT=BASE/'backups/releases'/NAME
SOURCE=KIT/'source'
sys.path[:0]=[str(Path(__file__).resolve().parent),str(SOURCE/'scripts/security_release')]
from ha_state import capture,replace
from platform_transaction import install_hooks as install_platform_hooks


def load_router():
 sys.path.insert(0,str(SOURCE/'scripts/router_release'))
 spec=importlib.util.spec_from_file_location('security_router_activation',SOURCE/'scripts/router_release/activate.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module


def ha_command(core,manifest,previous=False):
 image=manifest['baseline']['homeassistant']['image'] if previous else manifest['homeassistant_image']
 override=KIT/'private/ha-selected-image.json'
 core.platform().write_json(override,{'services':{'homeassistant':{'image':image,'pull_policy':'never'}}})
 core.call(['docker','compose','-p',manifest['homeassistant_project'],'-f',str(BASE/'homeassistant/docker-compose.yml'),
            '-f',str(override),'up','-d','--no-build','--pull','never','homeassistant'],timeout=300)


def ha_ready(core,manifest,previous=False):
 expected=manifest['baseline']['homeassistant']['image'] if previous else manifest['homeassistant_image']
 model=json.loads((BASE/'infra/docker-compose.yml').read_text())
 files=model['services']['homecontrol-ha-growatt-poller'].get('env_file',[])
 values={}
 for item in files:
  path=Path(item['path']);core.platform().no_symlinks(path)
  if not path.is_relative_to(BASE/'infra/ssh'):raise ValueError('Unexpected HA credential source')
  for line in path.read_text().splitlines():
   key,separator,value=line.partition('=')
   if separator:values[key]=value
 token=values.get('HA_TOKEN','').strip()
 if not token:raise ValueError('Existing HA poller token is missing')
 expected_file=KIT/'private/ha-expected-entities.json'
 for _ in range(180):
  try:
   row=json.loads(core.call(['docker','inspect','homeassistant']).stdout)[0]
   if row['Image']!=expected or not row['State']['Running']:raise ValueError('Home Assistant image not running')
   request=urllib.request.Request('http://127.0.0.1:8123/api/states',headers={'Authorization':'Bearer '+token})
   with urllib.request.urlopen(request,timeout=5) as response:
    rows=json.load(response);status=response.status
   if status!=200 or not isinstance(rows,list):raise ValueError('Authenticated Home Assistant API not available')
   available={r['entity_id'] for r in rows if r.get('state') not in ('unknown','unavailable')}
   if previous and not expected_file.exists():
    registry=json.loads((BASE/'homeassistant/config/.storage/core.entity_registry').read_text())
    growatt={r['entity_id'] for r in registry['data']['entities'] if r.get('platform')=='growatt_server' and not r.get('disabled_by')}
    core.platform().write_json(expected_file,sorted(growatt&available))
   wanted=set(json.loads(expected_file.read_text())) if expected_file.exists() else set()
   if not wanted<=available:raise ValueError('Previously available Growatt entities are not ready')
   return {'ok':True,'image':expected,'http_status':status,'authenticated_api':True,
           'previously_available_growatt_entities_preserved':len(wanted),'state_count':len(rows)}
  except (ValueError,OSError,RuntimeError):time.sleep(2)
 raise RuntimeError('Home Assistant readiness failed')


def preflight(core,manifest):
 if core.digest(BASE/'homeassistant/docker-compose.yml')!=manifest['previous_ha_compose_sha256']:
  raise ValueError('Home Assistant Compose changed since preparation')
 if core.digest(BASE/'homeassistant/config/configuration.yaml')!=manifest['previous_ha_configuration_sha256']:
  raise ValueError('Home Assistant configuration changed since preparation')
 current=json.loads(core.call(['docker','inspect','homeassistant']).stdout)[0]
 if current['Image']!=manifest['baseline']['homeassistant']['image'] or current['Id']!=manifest['baseline']['homeassistant']['id']:
  raise ValueError('Home Assistant baseline changed')
 baseline=ha_ready(core,manifest,previous=True)
 core.platform().write_json(KIT/'evidence/ha-before-live.json',baseline,0o644)
 # Full protected auth/config copy is checked under real local sudo before any
 # service is stopped. The offline lab mounts only this copy, never live config.
 identity=uuid.uuid4().hex
 source=KIT/'private'/('ha-preflight-input-'+identity)
 capture(BASE/'homeassistant/config',source)
 work=KIT/'private'/('ha-preflight-work-'+identity)
 core.call([sys.executable,str(SOURCE/'scripts/hc_ha_upgrade_probe.py'),
            '--image',manifest['homeassistant_image'],'--input',str(source),'--work',str(work),
            '--report',str(KIT/'evidence/ha-full-private-preflight.json')],timeout=600)
 proof=json.loads((KIT/'evidence/ha-full-private-preflight.json').read_text())
 if not proof['ok'] or not proof['rows_preserved']:raise ValueError('Full private HA preflight failed')


def postgres_ready(core):
 # A stable-distribution OS update can change locale data while retaining the
 # database files. Reject a mismatch; do not silently refresh or reindex data.
 query="""SELECT json_build_object('major',current_setting('server_version_num')::int/10000,
 'recorded',datcollversion,'actual',pg_database_collation_actual_version(oid))
 FROM pg_database WHERE datname=current_database();"""
 result=core.call(['docker','exec','-i','homecontrol-postgres','sh','-c',
  'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],input=query.encode())
 row=json.loads(result.stdout)
 if row['major']!=16 or row['recorded']!=row['actual']:raise ValueError('PostgreSQL version/collation mismatch')
 return {'ok':True,**row}


def install_hooks(router,manifest):
 core=router.core
 original_targets=core.target_files
 original_install=core.install_files
 original_stop=core.Cutover.stop
 original_start=core.Cutover.start
 original_verify=core.Cutover.verify
 original_rollback=core.rollback
 original_router_hooks=router.install_hooks
 state=KIT/'private/ha-state.json'
 backup=KIT/'private/ha-before-cutover'

 def targets():
  return list(dict.fromkeys(original_targets()+[BASE/'homeassistant/docker-compose.yml']))

 def install(m):
  original_install(m)
  core.atomic_copy(SOURCE/'homeassistant/docker-compose.yml',BASE/'homeassistant/docker-compose.yml')

 def stop(context):
  core.phase('stop_homeassistant')
  # Journal the attempted stop first: an interrupt after Docker accepts it
  # must still restart the previous HA owner during rollback.
  core.platform().write_json(state,{'stopped':True,'data_may_be_upgraded':False})
  core.call(['docker','stop','--time','60','homeassistant'],timeout=90)
  # Capture again after the real HA owner has stopped. This is the authoritative
  # rollback database, independent of the earlier online preflight copy.
  receipt=capture(BASE/'homeassistant/config',backup)
  if not receipt['sqlite'].get('consistent_online_copy'):raise ValueError('Missing HA rollback database')
  original_stop(context)

 def start(context):
  original_start(context)
  core.platform().write_json(state,{'stopped':True,'data_may_be_upgraded':True})
  ha_command(core,manifest)

 def verify(context):
  original_verify(context)
  core.platform().write_json(KIT/'evidence/postgres-live-acceptance.json',postgres_ready(core),0o644)
  proof=ha_ready(core,manifest)
  core.platform().write_json(KIT/'evidence/ha-live-acceptance.json',proof,0o644)

 def rollback(m):
  # A later installed release must be rejected before stopping any HA process.
  marker=json.loads((BASE/'infra/access-release.json').read_text())
  if marker['release'] not in (core.NAME,core.OLD):raise ValueError('Later release blocks HA rollback')
  transition=json.loads((core.STATE/'transition.json').read_text())
  if transition.get('release')!=core.NAME:raise ValueError('HA rollback transition mismatch')
  core.idle()
  status=json.loads(state.read_text()) if state.exists() else {}
  if status.get('stopped'):
   core.call(['docker','stop','--time','60','homeassistant'],allowed=(0,1),timeout=90)
   if status.get('data_may_be_upgraded'):
    quarantine=replace(backup,BASE/'homeassistant/config')
    if quarantine is not None:
     shutil.move(str(quarantine),str(KIT/'private'/('ha-failed-config-'+uuid.uuid4().hex)))
    core.platform().write_json(state,{'stopped':True,'data_may_be_upgraded':False,'database_restored':True})
  original_rollback(m)
  if status.get('stopped'):
   ha_command(core,m,previous=True)
   ha_ready(core,m,previous=True)

 def router_hooks(candidate):
  pending=original_router_hooks(candidate)
  # Router hooks wrap target/install/verify; preserve their behavior, then add
  # HA handling around the resulting transaction exactly once.
  nonlocal original_targets,original_install,original_verify
  original_targets=core.target_files;original_install=core.install_files;original_verify=core.Cutover.verify
  core.target_files=targets;core.install_files=install
  core.Cutover.stop=stop;core.Cutover.start=start;core.Cutover.verify=verify
  return pending

 router.install_hooks=router_hooks
 core.rollback=rollback
 return rollback


def main(action='activate'):
 if os.geteuid()!=0:raise PermissionError('Run this sealed command with sudo in the local HC terminal')
 router=load_router();core=router.core
 manifest=core.verify()
 install_platform_hooks(core,manifest)
 rollback=install_hooks(router,manifest)
 if action=='rollback':
  # The reviewed router path takes its operator lock and validates transition.
  return router.main('rollback')
 if core.STATE.exists():raise ValueError('Existing transition: inspect or explicitly roll back, do not repeat activation')
 core.guard_runtime(manifest)
 print('Teljes privát HA-másolat és offline előellenőrzés; az éles szolgáltatások még futnak.',flush=True)
 preflight(core,manifest)
 print('HA-előellenőrzés sikeres. Ellenőrzött mentés és visszagörgethető r18 átállítás indul.',flush=True)
 router.main('activate')


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('activate','rollback'),nargs='?',default='activate');a=p.parse_args()
 signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(InterruptedError('Terminated')))
 try:main(a.action)
 except BaseException as error:
  # Exception details and library/server responses may contain configuration.
  print('Az r18 művelet megállt: '+type(error).__name__+'. A privát állapotot ellenőrizni kell.',file=sys.stderr)
  raise SystemExit(1)
