import json,os,subprocess,sys,tarfile,threading
from pathlib import Path
B=Path('/srv/docker/homecontrol');P=Path('/tmp/hc41-44-20261029');R=P/'isolation'
R.mkdir(exist_ok=True);R.chmod(0o755)
sys.path[:0]=[str(B/'infra/backend'),str(B/'scripts/hostops')]
from server import CapabilityServer,OperationJournal
from executor import DockerCapabilities,Executor
from backup_protocol import atomic_json,seal,verify_archive
import backup_service
from scoped_ai_power_coordination import ScopedAiPowerCoordinator

name='hc44-lab-target';foreign='hc44-lab-foreign'
created=[];server=thread=None
report={'production_commands_sent':False,'lab_policy_override_for_synthetic_restore':True}
def run(args,**kwargs):
 r=subprocess.run(args,capture_output=True,text=True,**kwargs)
 if r.returncode:raise RuntimeError(r.stderr)
 return r.stdout
try:
 for n in (name,foreign):
  assert subprocess.run(['docker','inspect',n],capture_output=True).returncode!=0,'Lab name already exists'
 for n in (name,foreign):
  run(['docker','run','-d','--name',n,'--network','none','--label','com.docker.compose.project=hc44-test',
       '--label','com.docker.compose.service=probe','--entrypoint','python','homecontrol-backend:hc-read-models-20261028-r8',
       '-u','-c','import signal,time;signal.signal(signal.SIGTERM,lambda *a:exit(0));print("hc44-synthetic-log",flush=True);time.sleep(600)']);created.append(n)
 original=json.loads(run(['docker','inspect',name]))[0]
 backup=R/'backups';backup.mkdir(exist_ok=True)
 for filename in ('homecontrol-backup.lock','ai-backup.lock'):
  p=backup/filename;p.touch();p.chmod(0o666)
 state=backup/'ai-control';state.mkdir(exist_ok=True);state.chmod(0o777)
 source=R/'source';source.mkdir(exist_ok=True);(source/'file.txt').write_text('original')
 archive_source=R/'archive-source';(archive_source/'scripts').mkdir(parents=True,exist_ok=True)
 (archive_source/'scripts/file.txt').write_text('trusted restored content');seal(archive_source,'local',{})
 archive=backup/'homecontrol_hostops_fixture.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:tar.add(archive_source,arcname='backup')
 checked=verify_archive(archive)
 atomic_json(str(archive)+'.complete.json',dict(version=1,completed=True,name=archive.name,timestamp='2026-10-29T12:00:00+00:00',mtime_ns=archive.stat().st_mtime_ns,**checked))
 os.environ['HC_BACKUP_DIR']=str(backup);os.environ['HC_RESTORE_STAGING_DIR']=str(R/'stage')
 backup_service.ai_disabled=lambda:False
 backup_service.AiPowerCoordinator=ScopedAiPowerCoordinator
 service=backup_service.BackupService(lambda *a:None,lambda *a:None);service.restore_targets={'scripts':source}
 ipc=R/'ipc';ipc.mkdir(exist_ok=True);ipc.chmod(0o755)
 sock=ipc/'operations.sock'
 if sock.exists():sock.unlink()
 server=CapabilityServer(sock,Executor(DockerCapabilities(containers={'probe':name},project='hc44-test'),service),OperationJournal(R/'jobs'),allowed_uid=10001)
 sock.chmod(0o666)  # Fixture only: server enforces UID 10001 independently.
 thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05});thread.start()
 args=['docker','run','--rm','--name','hc44-lab-api','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
       '--tmpfs','/tmp:rw,exec,nosuid,nodev,size=64m','-e','PYTHONPATH=/app','-v',str(ipc)+':/ipc:ro','-v',str(source)+':/protected/source:ro',
       '-v',str(backup)+':/protected/backups:ro','-v',str(state)+':/protected/backups/ai-control:rw']
 for filename in ('homecontrol-backup.lock','ai-backup.lock'):args+=['-v',str(backup/filename)+':/protected/backups/'+filename+':rw']
 args+=['-v',str(P/'isolated_client.py')+':/check.py:ro','--entrypoint','python','hc44-backend-test:20261029','/check.py']
 output=run(args);(P/'isolation-client.log').write_text(output);report.update(json.loads(output.strip().splitlines()[-1]))
 after=json.loads(run(['docker','inspect',name]))[0]
 assert after['State']['StartedAt']!=original['State']['StartedAt']
 assert after['Id']==original['Id']
 report['real_disposable_container_restarted']=True
 denied_code="from host_operations_client import HostOperationsClient,HostOperationsUnavailable\ntry:HostOperationsClient('/ipc/operations.sock').call('containers')\nexcept HostOperationsUnavailable:print('wrong UID denied')\nelse:raise AssertionError('wrong UID accepted')"
 denied=run(['docker','run','--rm','--user','10002:10002','--network','none','--read-only','--cap-drop','ALL',
    '-e','PYTHONPATH=/app','-v',str(ipc)+':/ipc:ro','--entrypoint','python','hc44-backend-test:20261029','-c',denied_code])
 assert 'wrong UID denied' in denied
 report['wrong_peer_uid_denied']=True
 report['host_executor_test_uid']=os.getuid()
 report['fixture_socket_mode']='0666 (UID enforcement still active)'
 report['production_socket_mode']='0660; requires supervised host installation'
 report['no_container_received_docker_socket']=True
 assert (source/'file.txt').read_text()=='trusted restored content'
finally:
 if server:
  server.shutdown();server.server_close()
  if thread:thread.join(5)
  (R/'ipc/operations.sock').unlink(missing_ok=True)
 for n in ['hc44-lab-api',*created]:subprocess.run(['docker','rm','-f',n],capture_output=True)
 report['lab_containers_removed']=True
 (P/'isolation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
