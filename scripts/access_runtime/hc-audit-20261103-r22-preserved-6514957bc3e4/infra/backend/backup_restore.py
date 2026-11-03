"""Validated, journalled file restores. Never extract an archive onto a live tree."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import uuid

from backup_protocol import atomic_json, verify_archive, read_json, sha256


def canonical(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('Invalid restore path')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe restore path')
    return path.as_posix()


def archive_index(archive):
    result = {}; root = None
    for member in archive.getmembers():
        name = canonical(member.name)
        parts = PurePosixPath(name).parts
        if root is None: root = parts[0]
        if parts[0] != root: raise ValueError('Archive must have one root')
        if len(parts) == 1:
            if not member.isdir(): raise ValueError('Invalid archive root')
            continue
        rel = '/'.join(parts[1:])
        if rel in result: raise ValueError('Duplicate archive member: ' + rel)
        result[rel] = member
    if not result: raise ValueError('Empty archive')
    return result, root


def destination(relative, targets, allow_final_link=False):
    rel = canonical(relative)
    for component in sorted(targets, key=len, reverse=True):
        if rel == component or rel.startswith(component + '/'):
            root = Path(targets[component]).absolute()
            suffix = rel[len(component):].lstrip('/')
            out = root / suffix
            # Reject symlinks even if they currently point inside the boundary.
            # This also prevents compare from reading through a directory link.
            for parent in reversed(out.parents):
                if parent.is_symlink(): raise ValueError('Symlink in restore destination')
            if out.is_symlink() and not allow_final_link: raise ValueError('Symlink at restore destination')
            if out != root and root not in out.parents: raise ValueError('Destination escape')
            return out
    raise ValueError('Unsupported restore component: ' + rel.split('/')[0])


@contextmanager
def parent_fd(path, create=False, created=None):
    """Walk from / using directory descriptors; never follow a parent symlink."""
    path = Path(path).absolute()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    current = Path('/')
    try:
        for part in path.parent.parts[1:]:
            current /= part
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create: raise
                os.mkdir(part, 0o755, dir_fd=fd)
                if created is not None: created.append(str(current))
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        yield fd, path.name
    finally:
        os.close(fd)


def read_current(path, max_bytes=300000):
    try:
        with parent_fd(path) as (fd, name):
            file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(file_fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode): raise ValueError('Compare requires a regular file')
                if info.st_size > max_bytes: raise ValueError('Current file is too large for compare')
                return stream.read(max_bytes+1)
    except FileNotFoundError:
        return None


@contextmanager
def restore_lock(root):
    Path(root).mkdir(parents=True, exist_ok=True)
    with (Path(root)/'homecontrol-backup.lock').open('a+b') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Backup/restore is busy')
        yield


def _info(path):
    try: value = path.lstat()
    except FileNotFoundError: return None
    if path.is_symlink(): raise ValueError('Existing symlink must be removed explicitly')
    if not (stat.S_ISREG(value.st_mode) or stat.S_ISDIR(value.st_mode)):
        raise ValueError('Special destination file')
    return {'mode': stat.S_IMODE(value.st_mode) & 0o777, 'mtime_ns': value.st_mtime_ns,
            'atime_ns': value.st_atime_ns, 'uid': value.st_uid, 'gid': value.st_gid,
            'type': 'dir' if stat.S_ISDIR(value.st_mode) else 'file'}


def _install(entry, stage, created):
    path = Path(entry['destination']); kind = entry['type']
    with parent_fd(path, create=True, created=created) as (fd, name):
        if kind == 'dir':
            try: os.mkdir(name, 0o755, dir_fd=fd); created.append(str(path))
            except FileExistsError:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode): raise ValueError('Directory destination collision')
            return
        temporary = '.hc-restore-' + uuid.uuid4().hex
        try:
            if kind == 'symlink':
                os.symlink(entry['link'], temporary, dir_fd=fd)
            elif kind == 'hardlink':
                with parent_fd(entry['link_destination']) as (source_fd, source_name):
                    info = os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode): raise ValueError('Hardlink target changed')
                    os.link(source_name, temporary, src_dir_fd=source_fd, dst_dir_fd=fd, follow_symlinks=False)
            else:
                output_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                with os.fdopen(output_fd, 'wb') as output, (stage/entry['payload']).open('rb') as source:
                    shutil.copyfileobj(source, output)
                    os.fchmod(output.fileno(), entry['mode'])
                    before = entry.get('before') or {}
                    if 'uid' in before and os.geteuid() == 0:
                        os.fchown(output.fileno(), before['uid'], before['gid'])
                    os.fsync(output.fileno())
            if kind != 'hardlink':
                os.utime(temporary, ns=(entry['mtime_ns'], entry['mtime_ns']), dir_fd=fd, follow_symlinks=False)
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try: os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError: pass


def restore(archive_path, selections, mode, confirm, targets, staging_root, lock_root):
    if mode not in ('staging', 'in_place'): raise ValueError('Unknown restore mode')
    if mode == 'in_place' and confirm != 'RESTORE': raise ValueError('RESTORE confirmation is required')
    if not isinstance(selections, (list, tuple)) or not selections: raise ValueError('Select restore paths')
    selected = [canonical(item) for item in selections]
    run_id = uuid.uuid4().hex
    staging_root = Path(staging_root)
    with restore_lock(lock_root):
        staging_root.mkdir(parents=True, exist_ok=True)
        run = staging_root/run_id; run.mkdir(mode=0o700)
        payload = run/'payload'; payload.mkdir(mode=0o700)
        output = run/'files'
        journal_path = run/'journal.json'
        entries = []
        try:
            with tarfile.open(archive_path, 'r:gz') as archive:
                index, archive_root = archive_index(archive)
                integrity = 'legacy_unverified'
                if 'SHA256SUMS.txt' in index:
                    checked=verify_archive(archive_path); integrity = 'sha256_verified'
                    receipt=read_json(str(archive_path)+'.complete.json')
                    if receipt and receipt.get('completed') and receipt.get('sha256')!=checked['sha256']:
                        raise ValueError('Archive differs from its completed receipt')
                for choice in selected:
                    if not any(rel == choice or rel.startswith(choice+'/') for rel in index):
                        raise ValueError('Selected path missing from archive: ' + choice)
                chosen = {rel: member for rel, member in index.items()
                          if any(rel == item or rel.startswith(item+'/') for item in selected)}
                for rel, member in chosen.items():
                    if mode == 'in_place' and rel.split('/')[0] == 'postgres':
                        raise ValueError('Database dumps can only be restored to staging')
                    out = destination(rel, targets) if mode == 'in_place' else destination(rel, {rel.split('/')[0]: output/rel.split('/')[0]})
                    kind = ('file' if member.isfile() else 'dir' if member.isdir() else
                            'symlink' if member.issym() else 'hardlink' if member.islnk() else None)
                    if kind is None: raise ValueError('Special archive member is not restorable: ' + rel)
                    before = _info(out)
                    if before and (before['type'] == 'dir') != (kind == 'dir'):
                        raise ValueError('Destination type collision: ' + rel)
                    row = dict(path=rel, destination=str(out), type=kind, mode=member.mode & 0o777,
                               mtime_ns=int(member.mtime*1000000000), before=before, state='prepared')
                    if member.issym():
                        link = canonical(member.linkname)  # relative, no ..; explicit conservative policy
                        linked = str(PurePosixPath(rel).parent/link)
                        if linked.split('/')[0] != rel.split('/')[0]: raise ValueError('Cross-component link')
                        row['link'] = link
                    elif member.islnk():
                        link = canonical(member.linkname)
                        prefix = archive_root+'/'
                        if not link.startswith(prefix): raise ValueError('Hardlink outside archive root')
                        link = link[len(prefix):]
                        if link not in chosen or not chosen[link].isfile():
                            raise ValueError('Select the regular hardlink target as well: ' + rel)
                        row['link_destination'] = str(destination(link, targets) if mode == 'in_place' else output/link)
                    elif member.isfile():
                        row['payload'] = str(len(entries))
                        with archive.extractfile(member) as source, (payload/row['payload']).open('xb') as target:
                            shutil.copyfileobj(source, target)
                            target.flush(); os.fsync(target.fileno())
                    entries.append(row)
                # No archive link may be an ancestor of another selected path.
                links = [row['path'] for row in entries if row['type'] in ('symlink','hardlink')]
                if any(rel.startswith(link+'/') for link in links for rel in chosen):
                    raise ValueError('Archive member beneath a link')
            # Finish every preimage before the first destination change.
            for position, row in enumerate(entries):
                if row['before'] and row['before']['type'] == 'file':
                    row['preimage'] = 'before-'+str(position)
                    with parent_fd(row['destination']) as (fd, name):
                        source_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                        with os.fdopen(source_fd, 'rb') as source, (payload/row['preimage']).open('xb') as saved:
                            shutil.copyfileobj(source, saved)
                            saved.flush(); os.fsync(saved.fileno())
            entries.sort(key=lambda row: (row['type'] != 'dir', row['type'] == 'hardlink', row['path'].count('/'), row['path']))
            # Journal missing parents before mkdir, including the crash window
            # between creating a directory and committing the next file state.
            planned_directories=set()
            for row in entries:
                directory=Path(row['destination']) if row['type']=='dir' else Path(row['destination']).parent
                while not directory.exists():
                    planned_directories.add(str(directory))
                    directory=directory.parent
            journal = dict(version=1, run_id=run_id, mode=mode, state='prepared', integrity=integrity,
                           target=str(output) if mode == 'staging' else 'in-place', entries=entries,
                           created_dirs=sorted(planned_directories,key=lambda name:(len(Path(name).parts),name)))
            atomic_json(journal_path, journal, mode=0o600)
        except Exception:
            shutil.rmtree(run)
            raise
        try:
            journal['state'] = 'applying'; atomic_json(journal_path, journal, mode=0o600)
            for row in entries:
                row['state'] = 'applying'; atomic_json(journal_path, journal, mode=0o600)
                _install(row, payload, journal['created_dirs'])
                row['state'] = 'applied'; atomic_json(journal_path, journal, mode=0o600)
            # Directory metadata follows child creation, deepest first.
            for row in reversed(entries):
                if row['type'] == 'dir':
                    with parent_fd(row['destination']) as (fd, name):
                        directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        try:
                            os.fchmod(directory, row['mode'])
                            os.utime(directory, ns=(row['mtime_ns'],row['mtime_ns']))
                        finally: os.close(directory)
            journal['state'] = 'completed'
        except Exception as exc:
            journal['state'] = 'partial'; journal['error'] = type(exc).__name__ + ': ' + str(exc)
        try:
            atomic_json(journal_path, journal, mode=0o600)
        except OSError:
            journal['state']='partial'
            journal['error']='Could not persist final restore state; recover using this run ID after fixing storage'
        return report(journal)


def report(journal):
    return dict(ok=journal['state']=='completed', state=journal['state'], run_id=journal['run_id'],
                mode=journal['mode'], target=journal['target'], integrity=journal['integrity'],
                error=journal.get('error'), recovery_required=journal['state'] in ('partial','applying','prepared'),
                restored=[{'path': row['path'], 'destination': row['destination']} for row in journal['entries'] if row['state']=='applied'],
                remaining=[row['path'] for row in journal['entries'] if row['state']!='applied'])


def recoveries(staging_root):
    result=[]
    root=Path(staging_root)
    if not root.exists(): return result
    for run in sorted(root.iterdir(),key=lambda p:p.name):
        if run.is_symlink() or len(run.name)!=32 or any(c not in '0123456789abcdef' for c in run.name): continue
        try:
            journal=json.loads((run/'journal.json').read_text())
            if journal.get('state') in ('partial','applying','prepared'): result.append(report(journal))
        except (OSError,ValueError,KeyError): continue
    return result[-20:]


def _matches_current(row, run):
    """Do not overwrite a later operator edit during explicit recovery."""
    path=Path(row['destination'])
    try: info=path.lstat()
    except FileNotFoundError: return row['before'] is None
    if row['type']=='dir': return stat.S_ISDIR(info.st_mode)
    current_digest=None
    if stat.S_ISREG(info.st_mode):
        digest=hashlib.sha256()
        with parent_fd(path) as (fd,name):
            source_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
            with os.fdopen(source_fd,'rb') as source:
                for chunk in iter(lambda:source.read(1024*1024),b''): digest.update(chunk)
        current_digest=digest.hexdigest()
    if row['state']=='applying' and row.get('preimage') and stat.S_ISREG(info.st_mode):
        if current_digest==sha256(run/'payload'/row['preimage']): return True
    if row['type']=='symlink':
        if path.is_symlink() and os.readlink(path)==row['link']: return True
    elif row['type'] in ('file','hardlink') and stat.S_ISREG(info.st_mode):
        if row['type']=='hardlink':
            target=Path(row['link_destination'])
            if target.is_file() and not target.is_symlink() and target.stat().st_ino==info.st_ino: return True
        else:
            if current_digest==sha256(run/'payload'/row['payload']): return True
        # A process can die after journalling intent but before replacing a file.
        if row['state']=='applying' and row.get('preimage'):
            return current_digest==sha256(run/'payload'/row['preimage'])
    return False


def recover(run_id, staging_root, targets, lock_root, confirm):
    if not isinstance(run_id, str) or len(run_id)!=32 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid restore run ID')
    if confirm != 'ROLLBACK': raise ValueError('ROLLBACK confirmation is required')
    with restore_lock(lock_root):
        run = Path(staging_root)/run_id
        if run.is_symlink(): raise ValueError('Invalid recovery directory')
        journal_path = run/'journal.json'
        journal = json.loads(journal_path.read_text())
        if journal['state'] == 'rolled_back': return {**report(journal), 'ok': True}
        for row in journal['entries']:
            rel = canonical(row['path'])
            expected = destination(rel, targets, allow_final_link=True) if journal['mode']=='in_place' else destination(rel, {rel.split('/')[0]: run/'files'/rel.split('/')[0]}, allow_final_link=True)
            if str(expected) != row['destination']: raise ValueError('Recovery target mismatch')
            if row.get('preimage') and Path(row['preimage']).name != row['preimage']: raise ValueError('Invalid preimage')
            if row['state'] in ('applied','applying') and not _matches_current(row,run):
                raise ValueError('Recovery refused: destination changed since restore: '+rel)
        try:
            for row in reversed(journal['entries']):
                if row['state'] not in ('applied','applying'): continue
                path = Path(row['destination']); before = row['before']
                if before and before['type']=='file':
                    undo = {**row, **before, 'mtime_ns': before['mtime_ns'], 'type':'file', 'payload':row['preimage']}
                    _install(undo, run/'payload', [])
                elif not before and row['type'] != 'dir':
                    with parent_fd(path) as (fd, name):
                        try: os.unlink(name, dir_fd=fd)
                        except FileNotFoundError: pass
                elif before and before['type']=='dir':
                    with parent_fd(path) as (fd, name):
                        directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        try:
                            os.fchmod(directory, before['mode'])
                            os.utime(directory, ns=(before['atime_ns'],before['mtime_ns']))
                        finally: os.close(directory)
                row['state']='rolled_back'; atomic_json(journal_path,journal,mode=0o600)
            for directory in reversed(journal['created_dirs']):
                try: Path(directory).rmdir()
                except OSError: pass
            journal['state']='rolled_back'; journal.pop('error',None)
        except Exception as exc:
            journal['state']='partial'; journal['error']='Recovery failed: '+str(exc)
        atomic_json(journal_path,journal,mode=0o600)
        return {**report(journal), 'ok': journal['state']=='rolled_back'}
