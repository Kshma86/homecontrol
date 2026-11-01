"""Host-only HC-44 capability executor; never copied into the API image."""
import json,os,re,selectors,signal,socket,subprocess,time
from pathlib import Path
from backup_protocol import read_json,verify_archive
from deployment_policy import ai_disabled
from host_operations_client import HostBackupService

CONTAINERS={
 'backend':'homecontrol-backend','frontend':'homecontrol-frontend',
 'postgres':'homecontrol-postgres','pgbouncer':'homecontrol-pgbouncer',
 'mqtt':'homecontrol-mqtt','zigbee2mqtt':'zigbee2mqtt','ingest':'homecontrol-ingest',
 'tuya':'homecontrol-tuya-poller','x10':'homecontrol-xiaomi-x10',
 'climate':'homecontrol-gree-climate','solar':'homecontrol-ha-growatt-poller',
 'ai':'homecontrol-ai-server','proxy':'homecontrol-proxy','mdns':'homecontrol-mdns'}


def bounded_command(args,timeout=10,limit=2*1024*1024):
    """No shell; bounded process, total deadline and combined output."""
    env={k:v for k,v in os.environ.items() if k not in ('DOCKER_CONTEXT','DOCKER_HOST','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    env['DOCKER_HOST']='unix:///var/run/docker.sock'
    process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,start_new_session=True,env=env)
    deadline=time.monotonic()+timeout;data=bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while selector.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Host command deadline expired')
                for key,_ in selector.select(remaining):
                    part=os.read(key.fd,65536)
                    if not part:selector.unregister(key.fileobj);continue
                    data.extend(part)
                    if len(data)>limit:raise RuntimeError('Host command output limit exceeded')
        code=process.wait(timeout=max(.001,deadline-time.monotonic()))
        if code:raise RuntimeError('Host command failed; exit='+str(code))
        return bytes(data)
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL);process.wait()
        process.stdout.close()


def read_stats(target):
    # This is host-only code. The API image does not contain this adapter and
    # never receives the daemon socket. target was resolved by the allowlist.
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    deadline=time.monotonic()+2
    def remaining():
        value=deadline-time.monotonic()
        if value<=0:raise TimeoutError('Host stats deadline expired')
        return value
    try:
        client.settimeout(remaining());client.connect('/var/run/docker.sock')
        client.settimeout(remaining())
        client.sendall(('GET /containers/'+target+'/stats?stream=false HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n').encode())
        raw=bytearray()
        while True:
            client.settimeout(remaining());part=client.recv(65536)
            if not part:break
            raw.extend(part)
            if len(raw)>2*1024*1024:raise RuntimeError('Host stats output limit exceeded')
    finally:client.close()
    header,sep,body=bytes(raw).partition(b'\r\n\r\n')
    if not sep or b' 200 ' not in header.split(b'\r\n',1)[0]:raise RuntimeError('Host stats read failed')
    if b'transfer-encoding: chunked' in header.lower():
        decoded=bytearray()
        while body:
            size_raw,_,rest=body.partition(b'\r\n');size=int(size_raw.split(b';',1)[0],16)
            if size==0:break
            if len(rest)<size+2:raise RuntimeError('Incomplete host stats frame')
            decoded.extend(rest[:size]);body=rest[size+2:]
        body=bytes(decoded)
    stats=json.loads(body)
    cpu=stats.get('cpu_stats') or {};pre=stats.get('precpu_stats') or {}
    cpu_delta=(cpu.get('cpu_usage') or {}).get('total_usage',0)-(pre.get('cpu_usage') or {}).get('total_usage',0)
    system_delta=cpu.get('system_cpu_usage',0)-pre.get('system_cpu_usage',0)
    cpus=cpu.get('online_cpus') or len((cpu.get('cpu_usage') or {}).get('percpu_usage') or []) or 1
    mem=stats.get('memory_stats') or {};usage=mem.get('usage');limit=mem.get('limit')
    networks=stats.get('networks') or {};io=(stats.get('blkio_stats') or {}).get('io_service_bytes_recursive') or []
    return dict(cpu_percent=round(cpu_delta/system_delta*cpus*100,2) if system_delta>0 and cpu_delta>0 else 0.0,
        memory_usage_bytes=usage,memory_limit_bytes=limit,
        memory_percent=round(usage/limit*100,2) if isinstance(usage,(int,float)) and isinstance(limit,(int,float)) and limit>0 else None,
        network_rx_bytes=sum(int(r.get('rx_bytes') or 0) for r in networks.values()) if networks else None,
        network_tx_bytes=sum(int(r.get('tx_bytes') or 0) for r in networks.values()) if networks else None,
        block_read_bytes=sum(int(r.get('value') or 0) for r in io if str(r.get('op','')).lower()=='read') if io else None,
        block_write_bytes=sum(int(r.get('value') or 0) for r in io if str(r.get('op','')).lower()=='write') if io else None,
        pids=(stats.get('pids_stats') or {}).get('current'))


class DockerCapabilities:
    def __init__(self,run=bounded_command,containers=None,project='homecontrol',stats=read_stats):
        self.run=run;self.names=CONTAINERS if containers is None else containers;self.project=project;self.stats=stats

    def inventory(self):
        raw=self.run(['docker','ps','-a','--filter','label=com.docker.compose.project='+self.project,
                      '--format','{{json .}}'],timeout=3)
        result=[]
        for line in raw.splitlines():
            row=json.loads(line);name=row.get('Names')
            if name not in self.names.values():continue
            key=next(k for k,v in self.names.items() if v==name)
            result.append(dict(Id=row['ID'],Names=['/'+name],Image=row.get('Image',''),
                State=row.get('State',''),Status=row.get('Status',''),
                Labels={'com.docker.compose.service':key}))
        return result

    def target(self,ref):
        # Exact allowlist key/name or the complete advertised ID; no prefix guessing.
        if not isinstance(ref,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',ref):
            raise ValueError('Invalid container target')
        rows=self.inventory()
        matches=[r for r in rows if ref in (r['Id'],r['Names'][0][1:],r['Labels']['com.docker.compose.service'])]
        if len(matches)!=1:raise ValueError('Container is outside the allowed project/targets')
        return matches[0]['Id']

    def validate_restart(self,args):
        if set(args)!={'container'}:raise ValueError('Unexpected restart fields')
        target=self.target(args['container'])
        row=next(r for r in self.inventory() if r['Id']==target)
        if row['Names']==['/homecontrol-ai-server'] and ai_disabled():
            raise ValueError('AI operations are disabled by deployment policy')
        return target

    def dispatch(self,op,args):
        if op=='containers':
            if args:raise ValueError('Unexpected inventory fields')
            return self.inventory()
        if op in ('stats','logs','restart'):
            expected={'container','tail'} if op=='logs' else {'container'}
            if set(args)!=expected:raise ValueError('Unexpected container operation fields')
            target=self.target(args['container'])
            if op=='restart':
                self.validate_restart(args)
                self.run(['docker','restart','--time','10',target],timeout=18)
                return {'restart_requested':True}
            if op=='logs':
                n=args['tail']
                if type(n) is not int or not 20<=n<=3000:raise ValueError('Invalid log bound')
                return self.run(['docker','logs','--timestamps','--tail',str(n),target],timeout=5).decode(errors='replace')
            return self.stats(target)
        if op=='version':
            if args:raise ValueError('Unexpected version fields')
            return json.loads(self.run(['docker','version','--format','{{json .Server}}'],timeout=3))
        if op=='images':
            if args:raise ValueError('Unexpected image fields')
            return [{'image':row['Image']} for row in self.inventory()]
        raise ValueError('Unsupported Docker capability')


class Executor:
    def __init__(self,docker,backup):
        self.docker=docker;self.backup=backup

    def dispatch(self,op,args):
        if op!='backup':return self.docker.dispatch(op,args)
        if set(args)!={'method','values'} or not isinstance(args['values'],list):
            raise ValueError('Invalid backup capability')
        method=args['method'];values=args['values']
        if method not in HostBackupService.READS | HostBackupService.PAYLOADS:
            raise ValueError('Unsupported backup method')
        arity={'payload':0,'settings':0,'latest_info':0,'archives':0,'activity':0,
            'ai_shutdown_guard':0,'backup_plan':0,'update_settings_payload':1,
            'create_payload':0,'full_ai_backup_payload':0,'gitea_status_payload':0,
            'gitea_commit_payload':1,'gitea_restore_payload':1,'contents_payload':2,
            'compare_payload':2,'restore_payload':1,'recover_restore_payload':1}
        if len(values)!=arity[method]:raise ValueError('Unexpected backup arguments')
        if method in ('update_settings_payload','gitea_commit_payload','gitea_restore_payload','restore_payload','recover_restore_payload'):
            if type(values[0]) is not dict:raise ValueError('Backup object required')
        if method=='update_settings_payload':self.validate_settings(values[0])
        if method in ('contents_payload','compare_payload'):
            if not isinstance(values[0],str) or Path(values[0]).name!=values[0]:raise ValueError('Invalid archive name')
        if method=='gitea_commit_payload' and set(values[0])-{'message'}:raise ValueError('Unexpected git fields')
        if method=='gitea_restore_payload':
            data=values[0]
            if set(data)-{'ref'} or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]{0,119}',str(data.get('ref','main'))):
                raise ValueError('Invalid git ref')
        if method=='restore_payload':
            data=values[0]
            if set(data)-{'backup','paths','mode','confirm'}:raise ValueError('Unexpected restore fields')
            name=data.get('backup','')
            if not isinstance(name,str) or Path(name).name!=name:raise ValueError('Invalid archive name')
            if data.get('mode')=='in_place':
                # API cannot write archives/receipts. Only host-verified input may
                # overwrite executable source; unverified archives remain preview-only.
                path=self.backup.safe_path(name)
                receipt=read_json(str(path)+'.complete.json') or {}
                if not receipt.get('completed') or receipt.get('sha256')!=verify_archive(path)['sha256']:
                    raise ValueError('In-place restore requires a host-verified completed archive')
        if method=='recover_restore_payload':
            if set(values[0])-{'run_id','confirm'} or not re.fullmatch(r'[0-9a-f]{32}',str(values[0].get('run_id',''))):
                raise ValueError('Invalid restore recovery identity')
        context_methods={'update_settings_payload','create_payload','full_ai_backup_payload','gitea_commit_payload','restore_payload'}
        if method in context_methods:values=[*values,lambda *a:{}]
        return getattr(self.backup,method)(*values)

    def validate_settings(self,data):
        current=self.backup.settings()
        for key,value in data.items():
            if key not in self.backup.DEFAULT_SETTINGS:raise ValueError('Unknown backup setting')
            default=self.backup.DEFAULT_SETTINGS[key]
            if type(default) is bool:
                if type(value) is not bool:raise ValueError('Boolean backup setting required')
            elif type(default) is int:
                if type(value) is not int or not 1<=value<=365:raise ValueError('Invalid backup retention')
            elif key=='schedule_time':
                if not isinstance(value,str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',value):raise ValueError('Invalid backup time')
            elif key=='ai_weekly_backup_schedule':
                if not isinstance(value,str) or not re.fullmatch(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:[01][0-9]|2[0-3]):[0-5][0-9]',value):raise ValueError('Invalid weekly time')
            elif value!=current.get(key):
                raise ValueError('Host paths, credentials and destinations require host-side configuration: '+key)
