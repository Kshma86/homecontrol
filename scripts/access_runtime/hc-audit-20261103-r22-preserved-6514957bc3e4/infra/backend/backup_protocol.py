"""F6 backup receipts, bounded reads, queue and target state; stdlib only."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import tempfile
import time
from datetime import datetime, timezone
import uuid


RUN_ID = re.compile(r'^[0-9a-f]{32}$')
NEW_ARCHIVE = re.compile(r'^homecontrol_\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d_[0-9a-f]{32}\.tar\.gz$')
MODES = ('local', 'weekly', 'git', 'check', 'maintenance')


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def read_json(path, limit=131072):
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(limit+1)
        if len(data)>limit: return None
        result = json.loads(data)
        return result if isinstance(result,dict) else None
    except (OSError, ValueError):
        return None


def tail(path, lines=300, max_bytes=262144):
    """One bounded seek/read, including huge single-line and rotated files."""
    with Path(path).open('rb') as stream:
        size = stream.seek(0,os.SEEK_END)
        stream.seek(max(0,size-max_bytes))
        data = stream.read(max_bytes)
    if size>max_bytes:
        data = data.partition(b'\n')[2]  # discard incomplete first line
    return data.decode('utf-8',errors='replace').splitlines()[-max(1,min(int(lines),2000)):]


def lock_state(path):
    """Read-only inode probe. Unknown is distinct from an unlocked/missing file."""
    try:
        with Path(path).open('rb') as stream:
            try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return True
            fcntl.flock(stream,fcntl.LOCK_UN)
        return False
    except FileNotFoundError:
        return False
    except OSError:
        return None


def enqueue(root, mode, message=''):
    if mode not in ('local','weekly','git'): raise ValueError('Unsupported backup request mode')
    root = Path(root); run_id = uuid.uuid4().hex
    request = dict(version=1,run_id=run_id,mode=mode,source='web',state='queued',requested_at=now())
    if message: request['message']=str(message)[:256]
    atomic_json(root/'runs'/(run_id+'.json'), request)
    # The watched directory must contain only committed requests, even after a
    # killed enqueue. Temporary files stay outside it to avoid a .path busy loop.
    temporary=root/('queued-'+run_id+'.tmp')
    try:
        atomic_json(temporary,request)
        (root/'requests').mkdir(parents=True,exist_ok=True)
        os.replace(temporary,root/'requests'/(run_id+'.json'))
    except Exception:
        (root/'runs'/(run_id+'.json')).unlink(missing_ok=True)
        raise
    finally: temporary.unlink(missing_ok=True)
    return request


def jobs(root, limit=20):
    root=Path(root)
    try: paths=sorted((root/'runs').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:limit]
    except OSError: return []
    result=[]; held=lock_state(root/'homecontrol-backup.lock')
    current=read_json(root/'backup-state.json') or {}
    for path in paths:
        row=read_json(path)
        if not row: continue
        if row.get('state')=='running' and (held is False or current.get('run_id')!=row.get('run_id')):
            row={**row,'state':'interrupted','error':'Worker ended without a final result'}
        result.append(row)
    return result


def target(root, run_id, name, state, detail=''):
    if not RUN_ID.fullmatch(run_id) or state not in ('running','succeeded','failed','skipped'):
        raise ValueError('Invalid backup target update')
    root=Path(root); path=root/'runs'/(run_id+'.json')
    job=read_json(path)
    if not job or job.get('state')!='running': raise ValueError('No running backup job')
    item=dict(state=state,updated_at=now(),detail=detail[:500])
    job.setdefault('targets',{})[name]=item
    atomic_json(path,job)
    atomic_json(root/'backup-state.json',job)
    history=read_json(root/'backup-targets.json') or {}
    previous=history.get(name,{})
    history[name]={**previous,'last_status':item,'run_id':run_id}
    if state!='skipped': history[name]['last_attempt']=item
    if state=='succeeded': history[name]['last_success']=item['updated_at']
    if state=='failed': history[name]['last_failure']=item
    atomic_json(root/'backup-targets.json',history)


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def seal(directory, mode, coverage):
    directory=Path(directory)
    atomic_json(directory/'backup_manifest.json',dict(version=1,mode=mode,coverage=coverage,created_at=now()))
    files=sorted(p for p in directory.rglob('*') if p.is_file() and not p.is_symlink()
                 and p not in (directory/'SHA256SUMS.txt',directory/'MANIFEST.txt'))
    names=[p.relative_to(directory).as_posix() for p in files]
    (directory/'MANIFEST.txt').write_text('\n'.join(names)+'\n')
    files.append(directory/'MANIFEST.txt')
    rows=[]
    for path in files:
        name='./'+path.relative_to(directory).as_posix()
        escaped=name.replace('\\','\\\\').replace('\n','\\n')
        rows.append(('\\' if escaped!=name else '')+sha256(path)+'  '+escaped)
    (directory/'SHA256SUMS.txt').write_text('\n'.join(rows)+'\n')


def verify_archive(path):
    """Stream member bytes and verify the internal file checksum set, without extraction."""
    actual={}; expected=None; roots=set()
    with tarfile.open(path,'r|gz') as archive:
        for member in archive:
            root,sep,name=member.name.partition('/')
            roots.add(root)
            if not sep or not (member.isfile() or member.islnk()): continue
            if name in actual: raise ValueError('Duplicate archive member')
            if member.islnk():
                # GNU tar emits hardlinks after their data-bearing member. Reuse
                # only a digest already checked in this stream and archive root;
                # never extract a link or seek backwards through compressed data.
                link_root,link_sep,link_name=member.linkname.partition('/')
                if link_root!=root or not link_sep or link_name not in actual or name=='SHA256SUMS.txt':
                    raise ValueError('Invalid or unresolved archive hardlink')
                actual[name]=actual[link_name]
                continue
            stream=archive.extractfile(member)
            if name=='SHA256SUMS.txt':
                data=stream.read(16*1024*1024+1)
                if len(data)>16*1024*1024: raise ValueError('Checksum manifest too large')
                expected={}
                for line in data.decode().splitlines():
                    escaped=line.startswith('\\'); line=line[1:] if escaped else line
                    if len(line)<67 or not re.fullmatch('[0-9a-f]{64}',line[:64]): raise ValueError('Invalid checksum manifest')
                    filename=line[66:]
                    if escaped:
                        filename=re.sub(r'\\([\\n])',lambda m:'\n' if m[1]=='n' else '\\',filename)
                    filename=filename.removeprefix('./')
                    if filename in expected: raise ValueError('Duplicate checksum entry')
                    expected[filename]=line[:64]
                continue
            digest=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
            actual[name]=digest.hexdigest()
    if len(roots)!=1 or not expected or actual!=expected:
        raise ValueError('Incomplete archive or internal checksum mismatch')
    return dict(sha256=sha256(path),size_bytes=Path(path).stat().st_size,verified_files=len(actual))


def publish(root, run_id, partial, final, mode, coverage):
    root=Path(root);partial=Path(partial);final=Path(final)
    if partial.parent!=root or final.parent!=root or final.exists(): raise ValueError('Invalid publish target')
    checked=verify_archive(partial)
    os.replace(partial,final)
    with final.open('rb') as stream: os.fsync(stream.fileno())
    receipt=dict(version=1,completed=True,name=final.name,run_id=run_id,mode=mode,
                 coverage=coverage,timestamp=now(),mtime_ns=final.stat().st_mtime_ns,**checked)
    atomic_json(root/(final.name+'.complete.json'),receipt)
    job=read_json(root/'runs'/(run_id+'.json'))
    if job:
        job['archive']=receipt;atomic_json(root/'runs'/(run_id+'.json'),job)
    return receipt


def inventory(root):
    root=Path(root);result=[]
    try: paths=list(root.glob('homecontrol_*.tar.gz'))
    except OSError: return []
    for path in paths:
        try:
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode): continue
            receipt=read_json(root/(path.name+'.complete.json'),8192)
            complete=bool(receipt and receipt.get('version')==1 and receipt.get('completed') is True
                and receipt.get('name')==path.name and receipt.get('size_bytes')==info.st_size
                and receipt.get('mtime_ns')==info.st_mtime_ns
                and re.fullmatch('[0-9a-f]{64}',str(receipt.get('sha256',''))))
            if not complete and NEW_ARCHIVE.fullmatch(path.name): continue
            row=dict(name=path.name,path=str(path),size_bytes=info.st_size,
                timestamp=receipt['timestamp'] if complete else datetime.fromtimestamp(info.st_mtime,timezone.utc).isoformat(),
                completed=complete,verification='verified' if complete else 'legacy_unverified')
            if complete: row.update(mode=receipt.get('mode'),coverage=receipt.get('coverage'),sha256=receipt['sha256'])
            result.append(row)
        except (OSError,KeyError,ValueError): continue
    return sorted(result,key=lambda r:(r['completed'],r['timestamp']),reverse=True)


def retention(root, days, current):
    # Unverified/partial/failed and legacy archives are preserved for explicit review.
    cutoff=time.time()-max(1,int(days))*86400
    for row in inventory(root):
        path=Path(row['path'])
        if row['completed'] and path.name!=current and path.stat().st_mtime<cutoff:
            path.unlink();path.with_name(path.name+'.complete.json').unlink(missing_ok=True)
