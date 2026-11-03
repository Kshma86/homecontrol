"""HC-44 fixed host capabilities. No Docker protocol or shell fallback."""
import json
import os
from pathlib import Path
import socket
import time
import uuid
from urllib.parse import urlsplit, parse_qs

REQUEST_LIMIT = 65536
RESPONSE_LIMIT = 4 * 1024 * 1024
OPERATIONS = frozenset(('containers', 'stats', 'logs', 'restart', 'version', 'images', 'backup', 'job'))


class HostOperationsUnavailable(RuntimeError):
    pass


class HostOperationsClient:
    def __init__(self, path=None):
        self.path = str(path or os.getenv('HC_HOST_OPS_SOCKET', '/run/hc-host-ops/operations.sock'))

    def call(self, operation, *, timeout=30, request_id=None, **args):
        if operation not in OPERATIONS:
            raise ValueError('Unsupported host operation')
        request_id = request_id or uuid.uuid4().hex
        body = json.dumps(dict(version=1, request_id=request_id, operation=operation, args=args)).encode()+b'\n'
        if len(body)>REQUEST_LIMIT:raise ValueError('Host request too large')
        deadline=time.monotonic()+max(.001,min(float(timeout),180))
        def remaining():
            value=deadline-time.monotonic()
            if value<=0:raise TimeoutError('Host operation deadline; outcome may be unknown: '+request_id)
            return value
        client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            client.settimeout(remaining());client.connect(self.path)
            client.settimeout(remaining());client.sendall(body)
            raw=bytearray()
            while not raw.endswith(b'\n'):
                client.settimeout(remaining());part=client.recv(min(65536,RESPONSE_LIMIT+1-len(raw)))
                if not part:raise HostOperationsUnavailable('Host reply incomplete: '+request_id)
                raw.extend(part)
                if len(raw)>RESPONSE_LIMIT:raise HostOperationsUnavailable('Host reply too large')
            try:
                result=json.loads(raw)
                if type(result) is not dict or type(result.get('ok')) is not bool:raise ValueError('Invalid host reply')
            except (ValueError,TypeError):
                raise HostOperationsUnavailable('Host reply protocol error: '+request_id) from None
            if result.get('request_id')!=request_id:raise HostOperationsUnavailable('Host reply identity mismatch')
            if not result.get('ok'):
                if result.get('kind')=='invalid':raise ValueError(result.get('error','Host request rejected'))
                raise HostOperationsUnavailable(result.get('error','Host operation failed'))
            return result['value']
        except OSError as exc:
            if isinstance(exc,TimeoutError):raise TimeoutError('Host operation deadline; query job '+request_id) from None
            raise HostOperationsUnavailable('Host executor unavailable; no fallback: '+request_id) from None
        finally:client.close()


def docker_capability_request(method, path, body=None, content_type='application/json', timeout=30):
    """Compatibility for the existing API; only named capabilities cross IPC."""
    if body is not None:raise ValueError('Docker request bodies are not permitted')
    client=HostOperationsClient()
    parsed=urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:raise ValueError('Unsupported Docker operation')
    parts=parsed.path.strip('/').split('/')
    if method=='GET' and path=='/containers/json?all=1':value=client.call('containers',timeout=timeout)
    elif method=='GET' and path=='/version':value=client.call('version',timeout=timeout)
    elif method=='GET' and path=='/images/json':value=client.call('images',timeout=timeout)
    elif method=='GET' and len(parts)==3 and parts[0]=='containers' and parts[2]=='logs':
        query=parse_qs(parsed.query)
        if set(query)!={'stdout','stderr','timestamps','tail'} or any(query[k]!=['1'] for k in ('stdout','stderr','timestamps')):
            raise ValueError('Unsupported log request')
        value=client.call('logs',container=parts[1],tail=int(query['tail'][0]),timeout=timeout)
        return value.encode(), 'HTTP/1.1 200 OK'
    elif method=='POST' and len(parts)==3 and parts[0]=='containers' and parts[2]=='restart' and parsed.query=='t=10':
        value=client.call('restart',container=parts[1],timeout=timeout)
    else:raise ValueError('Unsupported Docker operation')
    return json.dumps(value).encode(), 'HTTP/1.1 200 OK'


class HostBackupService:
    """The API holds no writable archive, settings, staging or source mounts."""
    READS = frozenset(('payload','settings','latest_info','archives','activity','ai_shutdown_guard','backup_plan'))
    PAYLOADS = frozenset(('update_settings_payload','create_payload','full_ai_backup_payload',
        'gitea_status_payload','gitea_commit_payload','gitea_restore_payload','contents_payload',
        'compare_payload','restore_payload','recover_restore_payload'))

    def __init__(self, client=None):
        self.client=client or HostOperationsClient()
        self.backup_root=Path(os.getenv('HC_BACKUP_DIR','/srv/docker/homecontrol/backups'))

    def __getattr__(self, method):
        if method not in self.READS | self.PAYLOADS:raise AttributeError(method)
        def invoke(*args):
            context=args[-1] if args and callable(args[-1]) else None
            actual=args[:-1] if context else args
            result=self.client.call('backup',method=method,values=list(actual),timeout=180)
            if method in self.PAYLOADS:
                payload,status=result
                if context and status<400:payload={**payload,'context':context('backup')}
                return payload,status
            return result
        return invoke
