import hashlib,json,os,stat,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path('/srv/docker/homecontrol');N='hc-audit-20261102-r19';R=B/'scripts/access_runtime'/N
assert os.geteuid()==0 and subprocess.check_output(['hostname'],text=True).strip()=='hc-restore-vm'
sys.path[:0]=[str(R/'scripts/access_release'),str(R/'scripts/hostops'),str(R/'infra/backend')]
from common import units
from installation_plan import validate_backend
from deployment_policy import public_status

def command(args):return subprocess.check_output(args,text=True,stderr=subprocess.PIPE)
health=None
for _ in range(100):
 try:
  health=json.load(urllib.request.urlopen('http://127.0.0.1:5000/health',timeout=2))
  if health.get('db_ok') and health.get('mqtt_ok'):break
 except Exception:pass
 time.sleep(.5)
else:raise AssertionError('Restored backend DB/MQTT health failed')
installed=json.loads((B/'backups/f6-installed.json').read_text())
assert installed['applied'] and installed['scope']=='system' and len(installed['units'])==14
for name,sha in installed['units'].items():
 assert hashlib.sha256((Path('/etc/systemd/system')/name).read_bytes()).hexdigest()==sha
for name,text in units(R).items():assert (Path('/etc/systemd/system')/name).read_text()==text
live_next={}
for name,wanted in installed['enabled'].items():
 actual=subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0
 assert actual==wanted,(name,actual,wanted)
 assert (subprocess.run(['systemctl','is-enabled','--quiet',name]).returncode==0)==wanted,(name,'enabled-state')
 if wanted and name.endswith('.timer'):
  value=command(['systemctl','show',name,'--property=NextElapseUSecRealtime,NextElapseUSecMonotonic']).strip()
  assert any(line.partition('=')[2].strip() not in ('','0','infinity','n/a') for line in value.splitlines()),(name,value)
  live_next[name]=value
assert len(installed['next_triggers'])==3
for base in (Path('/etc/systemd/user'),Path('/root/.config/systemd/user'),Path('/home/lab/.config/systemd/user')):
 assert not any(base.rglob('homecontrol-backup.timer')) and not any(base.rglob('homecontrol-log-maintenance.timer'))
container=json.loads(command(['docker','inspect','homecontrol-backend']))[0]
assert not validate_backend(container),validate_backend(container)
sock=Path('/run/homecontrol-hostops/operations.sock').stat()
assert sock.st_uid==0 and sock.st_gid==10001 and stat.S_IMODE(sock.st_mode)==0o660
probe='''import json,os
from pathlib import Path
from host_operations_client import HostOperationsClient
assert os.geteuid()==10001
rows=HostOperationsClient().call('containers');assert any('/homecontrol-backend' in r['Names'] for r in rows)
assert not Path('/var/run/docker.sock').exists()
for path in ('/app/forged','/srv/docker/homecontrol/scripts/forged','/srv/docker/homecontrol/backups/forged'):
 try:Path(path).write_text('denied')
 except OSError:pass
 else:raise AssertionError('protected write allowed')
print(json.dumps(dict(real_docker_inventory_count=len(rows),uid=10001,source_and_archive_writes_denied=True)))
'''
rpc=json.loads(command(['docker','exec','homecontrol-backend','python','-c',probe]))
receipt=Path('/var/lib/homecontrol-hostops/jobs')/('a'*32+'.json');assert json.loads(receipt.read_text())['state']=='uncertain'
policy=public_status();assert policy['restricted'] and not policy['ai_enabled'] and not policy['remote_backup_enabled']
rows=command(['docker','exec','homecontrol-postgres','sh','-c','psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from hc.measurement; select count(*) from hc.entity; select count(*) from information_schema.tables where table_schema=\'hc\';"']).strip().splitlines()
selection=json.loads(Path('/lab/restore/db-selection.json').read_text());assert hashlib.sha256(Path(selection['dump']).read_bytes()).hexdigest()==selection['dump_sha256']
result=dict(ok=True,real_systemd_pid1=command(['ps','-p','1','-o','comm=']).strip()=='systemd',system_scope_only=True,unit_count=14,access_unit_and_dropin_files=len(units(R)),next_triggers=live_next,enabled=installed['enabled'],unit_bytes_verified=True,backend_health=health,backend_nonroot_readonly_no_socket=True,root_socket_0660_10001=True,host_rpc=rpc,interrupted_job_uncertain=True,ai_offline_policy=policy,measurement_rows=int(rows[0]),entity_rows=int(rows[1]),hc_table_count=int(rows[2]),selected_dump_sha256=selection['dump_sha256'],hardware_network=False)
name=sys.argv[1] if len(sys.argv)>1 else 'restored-probe'
Path('/lab/'+name+'.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
