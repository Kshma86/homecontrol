"""Deduplicate only verified inactive root-owned image archives, preserving bytes."""
import hashlib
import os
from pathlib import Path
import stat
import uuid

BASE = Path('/srv/docker/homecontrol')
RELEASES = ('hc-audit-20261102-r19', 'hc-audit-20261102-r20')


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 ** 2), b''):
            result.update(chunk)
    return result.hexdigest()


def regular(path, uid):
    path = Path(path)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Symlink in image cache path')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
        raise ValueError('Unsafe immutable image archive metadata')
    return info


def paths(base=BASE):
    return [path for name in RELEASES for path in (
        base / 'backups/releases' / name / 'private/runtime/images/access-images.tar.gz',
        base / 'infra/ssh' / name / 'images/access-images.tar.gz')]


def deduplicate(selected, expected_sha256, *, apply=False, uid=0):
    selected = list(map(Path, selected))
    if not selected:
        raise ValueError('No image cache candidates')
    # Validate every input before replacing any directory entry. Credentials,
    # active r18 files, sealed source and operator-owned archives are not inputs.
    rows = []
    for path in selected:
        info = regular(path, uid)
        if sha(path) != expected_sha256:
            raise ValueError('Image archive checksum mismatch')
        rows.append((path, info))
    reference, before = rows[0]
    metadata = lambda info: (info.st_dev, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_size)
    if any(metadata(info) != metadata(before) for path, info in rows):
        raise ValueError('Cache archives have different ownership, mode or filesystem')
    original_inodes = {(info.st_dev, info.st_ino) for path, info in rows}
    changed = 0
    for path, info in rows[1:]:
        if (info.st_dev, info.st_ino) == (before.st_dev, before.st_ino):
            continue
        changed += 1
        if apply:
            current = regular(path, uid)
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
                raise ValueError('Image cache changed after validation')
            temporary = path.with_name('.image-link-' + uuid.uuid4().hex)
            try:
                os.link(reference, temporary)
                os.replace(temporary, path)
                fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            finally:
                temporary.unlink(missing_ok=True)
    if apply:
        if any(path.stat().st_ino != reference.stat().st_ino for path in selected):
            raise ValueError('Image cache deduplication verification failed')
        if sha(reference) != expected_sha256:
            raise ValueError('Image cache changed during deduplication')
    return {'ok': True, 'applied': apply, 'files': len(rows), 'previous_unique_inodes': len(original_inodes),
            'replacements': changed, 'archive_sha256': expected_sha256,
            'data_and_metadata_preserved': True, 'reference': str(reference)}


def link_archive(source, target, expected_sha256, *, uid=0):
    source, target = Path(source), Path(target)
    regular(source, uid)
    for path in (target, *target.parents):
        if path.is_symlink():
            raise ValueError('Symlink in new image cache path')
    if target.exists() or sha(source) != expected_sha256:
        raise ValueError('Existing cache target or changed archive')
    os.link(source, target)


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inventory',))
    parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Local sudo is required for private cache metadata')
    result = []
    for path in paths():
        if path.is_symlink():
            raise SystemExit('Unexpected symlink; no changes made')
        info = path.stat()
        result.append({'path': str(path), 'uid': info.st_uid, 'gid': info.st_gid,
                       'mode': oct(stat.S_IMODE(info.st_mode)), 'bytes': info.st_size,
                       'device': info.st_dev, 'inode': info.st_ino, 'links': info.st_nlink})
    print(json.dumps({'read_only': True, 'cache_files': result}, indent=2))
