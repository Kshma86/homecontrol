#!/usr/bin/env python3
"""HC-44 bounded Unix capability endpoint. No listener or changes on import."""
import argparse,hashlib,json,os,re,socket,socketserver,struct,sys,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'infra/backend'))
from backup_protocol import atomic_json,read_json,now
from host_operations_client import REQUEST_LIMIT,RESPONSE_LIMIT,OPERATIONS
from executor import DockerCapabilities,Executor


class OperationJournal:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=threading.Lock()
        self.restart_slots=threading.BoundedSemaphore(2)

    def lookup(self,identity):
        if not re.fullmatch(r'[0-9a-f]{32}',str(identity)):raise ValueError('Invalid job identity')
        row=read_json(self.root/(identity+'.json'),RESPONSE_LIMIT)
        if not row:raise ValueError('Unknown host job')
        return row

    def recover_abandoned(self):
        count=0
        for path in self.root.glob('*.json'):
            row=read_json(path,RESPONSE_LIMIT)
            if row and row.get('state') in ('queued','running'):
                row.update(state='uncertain',error='executor restarted; reconcile before retry',finished_at=now())
                atomic_json(path,row,0o600);count+=1
        return count

    def perform(self,identity,digest,operation,callback):
        with self.lock:
            path=self.root/(identity+'.json')
            previous=read_json(path,RESPONSE_LIMIT)
            if previous:
                if previous['digest']!=digest:raise ValueError('Host request identity reused with different content')
                if previous['state']=='completed':return previous['value']
                raise RuntimeError('Host job '+identity+' is '+previous['state']+'; no automatic replay')
            if len(list(self.root.glob('*.json')))>=1000:raise RuntimeError('Host job journal is full; host maintenance required')
            row=dict(version=1,request_id=identity,digest=digest,operation=operation,state='running',started_at=now())
            atomic_json(path,row,0o600)
        try:
            value=callback()
            encoded=json.dumps(value,default=str).encode()
            if len(encoded)>RESPONSE_LIMIT-2048:raise RuntimeError('Host result too large')
            row.update(state='completed',value=value,finished_at=now());atomic_json(path,row,0o600)
            return value
        except Exception as exc:
            row.update(state='failed' if isinstance(exc,ValueError) else 'uncertain',error=type(exc).__name__,finished_at=now())
            atomic_json(path,row,0o600);raise

    def enqueue_restart(self,identity,digest,callback,target=None):
        with self.lock:
            path=self.root/(identity+'.json')
            previous=read_json(path,RESPONSE_LIMIT)
            if previous:
                if previous['digest']!=digest:raise ValueError('Host request identity reused with different content')
                return {'restart_requested':True,'host_job_id':identity,'state':previous['state']}
            if len(list(self.root.glob('*.json')))>=1000:raise RuntimeError('Host job journal is full; host maintenance required')
            if not self.restart_slots.acquire(False):raise RuntimeError('Host restart capacity exhausted')
            row=dict(version=1,request_id=identity,digest=digest,operation='restart',target=target,state='queued',requested_at=now())
            try:atomic_json(path,row,0o600)
            except BaseException:self.restart_slots.release();raise
        def run():
            try:
                time.sleep(.4)  # Allow the API to send its accepted response first.
                row.update(state='running',started_at=now());atomic_json(path,row,0o600)
                value=callback();row.update(state='completed',value=value,finished_at=now())
            except Exception as exc:row.update(state='failed' if isinstance(exc,ValueError) else 'uncertain',error=type(exc).__name__,finished_at=now())
            finally:
                try:atomic_json(path,row,0o600)
                finally:self.restart_slots.release()
        threading.Thread(target=run,name='host-restart-'+identity,daemon=False).start()
        return {'restart_requested':True,'host_job_id':identity,'state':'queued'}


class CapabilityServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads=False
    block_on_close=True
    def __init__(self,path,executor,journal,allowed_uid=10001):
        self.executor=executor;self.journal=journal;self.allowed_uid=allowed_uid
        self.slots=threading.BoundedSemaphore(8)
        super().__init__(str(path),Handler)

    def process_request(self,request,client_address):
        if not self.slots.acquire(False):request.close();return
        try:super().process_request(request,client_address)
        except BaseException:self.slots.release();raise

    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        identity=None
        try:
            _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=self.server.allowed_uid:raise ValueError('Host peer UID is not allowed')
            self.request.settimeout(3)
            raw=self.rfile.readline(REQUEST_LIMIT+1)
            if len(raw)>REQUEST_LIMIT or not raw.endswith(b'\n'):raise ValueError('Invalid host request frame')
            data=json.loads(raw)
            if type(data) is not dict or set(data)!={'version','request_id','operation','args'} or data['version']!=1:
                raise ValueError('Invalid host request schema')
            identity=data['request_id'];op=data['operation'];args=data['args']
            if not isinstance(identity,str) or not re.fullmatch(r'[0-9a-f]{32}',identity) or op not in OPERATIONS or type(args) is not dict:
                raise ValueError('Invalid host capability')
            digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if op=='restart':
                # Validate the target before claiming acceptance or creating a job.
                target=self.server.executor.docker.validate_restart(args)
                value=self.server.journal.enqueue_restart(identity,digest,lambda:self.server.executor.dispatch(op,{'container':target}),target)
            elif op=='job':
                if set(args)!={'job_id'}:raise ValueError('Invalid job query')
                value=self.server.journal.lookup(args['job_id'])
            else:
                read=op not in ('restart','backup') or (op=='backup' and args.get('method') in ('payload','settings','latest_info','archives','activity','ai_shutdown_guard','backup_plan','gitea_status_payload','contents_payload','compare_payload'))
                callback=lambda:self.server.executor.dispatch(op,args)
                value=callback() if read else self.server.journal.perform(identity,digest,op,callback)
            response=dict(ok=True,request_id=identity,value=value)
        except Exception as exc:
            response=dict(ok=False,request_id=identity,kind='invalid' if isinstance(exc,ValueError) else 'unavailable',error=str(exc)[:500])
        raw=json.dumps(response,default=str).encode()+b'\n'
        if len(raw)>RESPONSE_LIMIT:raw=json.dumps(dict(ok=False,request_id=identity,error='Host reply exceeds bound')).encode()+b'\n'
        try:self.request.settimeout(3);self.wfile.write(raw)
        except OSError:pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket',default='/run/homecontrol-hostops/operations.sock')
    parser.add_argument('--journal',default='/var/lib/homecontrol-hostops/jobs')
    parser.add_argument('--api-uid',type=int,default=10001)
    parser.add_argument('--api-gid',type=int,default=10001)
    options=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('The host executor must be installed as root')
    import backup_service
    from scoped_ai_power_coordination import ScopedAiPowerCoordinator
    backup_service.AiPowerCoordinator=ScopedAiPowerCoordinator
    # No arbitrary Docker exec is needed for archive/staging operations.
    def forbidden(*a,**k):raise ValueError('General Docker API/exec is not a host capability')
    backup=backup_service.BackupService(forbidden,forbidden)
    socket_path=Path(options.socket)
    socket_path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    if socket_path.exists():raise SystemExit('Socket already exists; verify the previous executor before removing it')
    journal=OperationJournal(options.journal)
    journal.recover_abandoned()
    with CapabilityServer(socket_path,Executor(DockerCapabilities(),backup),journal,options.api_uid) as server:
        socket_path.chmod(0o660);os.chown(socket_path,0,options.api_gid)
        try:server.serve_forever(poll_interval=.2)
        finally:socket_path.unlink(missing_ok=True)


if __name__=='__main__':main()
