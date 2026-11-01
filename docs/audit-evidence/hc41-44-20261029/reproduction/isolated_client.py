import json,os,time
from pathlib import Path
from host_operations_client import HostOperationsClient,HostBackupService
from scoped_ai_power_coordination import ScopedAiPowerCoordinator
assert os.geteuid()==10001
assert not Path('/var/run/docker.sock').exists()
for path in ('/app/host_operations_client.py','/protected/source/file.txt','/protected/backups/forged.tar.gz'):
 try:Path(path).write_text('forbidden')
 except OSError:pass
 else:raise AssertionError('Unexpected write: '+path)
client=HostOperationsClient('/ipc/operations.sock')
rows=client.call('containers');assert len(rows)==1 and rows[0]['Names']==['/hc44-lab-target']
assert 'memory_usage_bytes' in client.call('stats',container='probe')
assert 'hc44-synthetic-log' in client.call('logs',container='probe',tail=20)
for op,args in [('restart',{'container':'homecontrol-backend'}),('restart',{'container':'probe','command':['id']})]:
 try:client.call(op,**args)
 except ValueError:pass
 else:raise AssertionError('Foreign operation accepted')
try:client.call('exec',container='probe',command=['id'])
except ValueError:pass
else:raise AssertionError('General exec accepted')
proxy=HostBackupService(client)
backup='homecontrol_hostops_fixture.tar.gz'
result,status=proxy.compare_payload(backup,'scripts/file.txt');assert status==200 and not result['same']
result,status=proxy.restore_payload({'backup':backup,'paths':['scripts/file.txt'],'mode':'in_place','confirm':'RESTORE'},lambda *a:{})
assert status==200 and result['ok'] and Path('/protected/source/file.txt').read_text()=='trusted restored content'
result,status=proxy.create_payload(lambda *a:{});assert status==202
coordinator=ScopedAiPowerCoordinator('/protected/backups')
with coordinator.locked() as state:coordinator.invalidate(state,'isolated non-root test')
assert coordinator.path.exists()
receipt=client.call('restart',container='probe')
for _ in range(100):
 job=client.call('job',job_id=receipt['host_job_id'])
 if job['state']=='completed':break
 time.sleep(.05)
assert job['state']=='completed',job
print(json.dumps(dict(uid=os.geteuid(),raw_docker_socket_absent=True,source_write_denied=True,archive_write_denied=True,
    inventory=True,stats=True,logs=True,foreign_restart_denied=True,arbitrary_command_denied=True,
    verified_host_restore=True,backup_queued=True,scoped_ai_state_writable=True,restart_completed=True)))
