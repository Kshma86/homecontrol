"""Verified backup-tree copy, with immutable releases and live lock inodes pinned."""
import base64
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import uuid

PINNED = ('releases', 'ai-control', 'ai-backup.lock', 'homecontrol-backup.lock')


class StorageError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise StorageError(reason)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''): value.update(block)
    return value.hexdigest()


def no_symlinks(path):
    for part in (Path(path), *Path(path).parents):
        require(not part.is_symlink(), 'Symlink in protected storage path')


def write_json(path, value, mode=0o600):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    with temporary.open('x') as stream:
        os.fchmod(stream.fileno(), mode)
        json.dump(value, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def attributes(path):
    info = path.lstat()
    common = {'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode), 'mtime_ns': info.st_mtime_ns}
    xattrs = {name: base64.b64encode(os.getxattr(path, name, follow_symlinks=False)).decode()
              for name in sorted(os.listxattr(path, follow_symlinks=False))}
    common['xattrs_sha256'] = hashlib.sha256(json.dumps(xattrs, sort_keys=True).encode()).hexdigest()
    if stat.S_ISLNK(info.st_mode): return {**common, 'type': 'symlink', 'target': os.readlink(path)}
    if stat.S_ISDIR(info.st_mode): return {**common, 'type': 'directory'}
    require(stat.S_ISREG(info.st_mode), 'Special file in backup tree')
    return {**common, 'type': 'file', 'bytes': info.st_size, 'sha256': digest(path)}


def inventory(root, only=None):
    root = Path(root); no_symlinks(root)
    rows = {}; links = defaultdict(list); unique_bytes = {}
    device = root.stat().st_dev
    for parent, directories, files in os.walk(root, followlinks=False):
        parent = Path(parent)
        if parent == root:
            directories[:] = [name for name in directories if name not in PINNED]
            files = [name for name in files if name not in PINNED]
        for name in list(directories) + files:
            path = parent / name; relative = str(path.relative_to(root))
            if path.is_symlink() and name in directories: directories.remove(name)
            if only is not None and relative not in only: continue
            row = attributes(path); rows[relative] = row
            info = path.lstat()
            if row['type'] != 'symlink': require(info.st_dev == device, 'Unexpected nested filesystem in backup data')
            if row['type'] == 'file':
                key = (info.st_dev, info.st_ino); links[key].append(relative); unique_bytes[key] = info.st_size
    return {'entries': rows, 'hardlinks': sorted(sorted(group) for group in links.values() if len(group) > 1),
            'unique_file_bytes': sum(unique_bytes.values())}


def verify_copy(expected, target):
    actual = inventory(target, only=set(expected['entries']))
    require(actual['entries'] == expected['entries'], 'Copied file content or metadata differs')
    require(actual['hardlinks'] == expected['hardlinks'], 'Copied hardlink relationships differ')
    return {'ok': True, 'entries': len(actual['entries']), 'bytes': actual['unique_file_bytes']}


def copy_tree(source, destination, run=subprocess.run):
    arguments = ['rsync', '-aHAXS', '--numeric-ids', '--checksum']
    arguments += ['--exclude=/' + name for name in PINNED]
    arguments += ['--', str(source) + '/', str(destination) + '/']
    run(arguments, check=True, capture_output=True, timeout=10800)
    # Rsync's delayed hardlink processing can change directory/symlink mtimes
    # after its attribute pass. Restore those explicitly, then verify exactly.
    for parent, directories, files in os.walk(source, followlinks=False):
        parent = Path(parent)
        if parent == Path(source):
            directories[:] = [name for name in directories if name not in PINNED]
            files = [name for name in files if name not in PINNED]
        for name in list(directories) + files:
            original = parent / name; info = original.lstat()
            if stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                target = Path(destination) / original.relative_to(source)
                os.utime(target, ns=(target.lstat().st_atime_ns, info.st_mtime_ns), follow_symlinks=False)


def placeholders(root, original):
    for name in PINNED:
        path = root / name
        require(not path.exists() and not path.is_symlink(), 'Existing pin placeholder')
        if name in ('releases', 'ai-control'): path.mkdir(mode=0o700)
        else: path.touch(mode=0o600)
    # Only the bind-mounted root is exposed; keep its original access model.
    info = original.stat(); os.chown(root, info.st_uid, info.st_gid); root.chmod(stat.S_IMODE(info.st_mode))


def cleanup_verified_duplicates(original, target, expected):
    require(inventory(original) == expected, 'Original rollback tree changed; duplicate cleanup refused')
    removed = skipped = 0
    for relative, row in expected['entries'].items():
        if row['type'] == 'directory': continue
        counterpart = target / relative
        if (not counterpart.exists() and not counterpart.is_symlink()) or attributes(counterpart) != row:
            skipped += 1; continue
        path = original / relative
        require(attributes(path) == row, 'Original changed during duplicate cleanup')
        path.unlink(); removed += 1
    directories = [name for name, row in expected['entries'].items() if row['type'] == 'directory']
    for name in sorted(directories, key=lambda value: len(Path(value).parts), reverse=True):
        try: (original / name).rmdir()
        except OSError: pass  # Changed/extra files are retained, never recursively deleted.
    return {'removed_verified_duplicate_entries': removed, 'retained_changed_entries': skipped,
            'logical_backup_files_deleted': False}
