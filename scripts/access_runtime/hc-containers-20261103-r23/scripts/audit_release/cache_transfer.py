"""Publish a verified immutable image cache across bind mounts without overwrite."""
import errno
import hashlib
import os
from pathlib import Path
import stat
import tempfile


def require(value, message):
    if not value: raise ValueError(message)


def no_symlinks(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink in image cache path')


def signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''): result.update(chunk)
    return result.hexdigest()


def transfer_archive(source, target, expected_sha256, *, uid=0):
    source, target = Path(source), Path(target)
    no_symlinks(source); no_symlinks(target)
    before = source.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid == uid and not before.st_mode & 0o7022,
            'Unsafe immutable image archive metadata')
    require(not target.exists(), 'Existing cache target')
    require(sha(source) == expected_sha256, 'Image archive checksum mismatch')
    require(signature(source.stat()) == signature(before), 'Image archive changed during validation')
    try:
        os.link(source, target)
    except OSError as error:
        if error.errno != errno.EXDEV: raise
    else:
        return {'method': 'hardlink', 'sha256': expected_sha256, 'bytes': before.st_size}

    # A shared st_dev does not imply that Linux permits a hardlink: separate
    # bind mounts are distinct VFS mounts. Copy only for the kernel's EXDEV.
    fd, temporary_name = tempfile.mkstemp(prefix='.hc-image-copy-', dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'wb') as output:
            source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(source_fd, 'rb') as stream:
                require(signature(os.fstat(stream.fileno())) == signature(before), 'Image archive changed before copy')
                attrs = {name: os.getxattr(stream.fileno(), name) for name in os.listxattr(stream.fileno())}
                copied = hashlib.sha256(); size = 0
                for chunk in iter(lambda: stream.read(1024 ** 2), b''):
                    output.write(chunk); copied.update(chunk); size += len(chunk)
                require(signature(os.fstat(stream.fileno())) == signature(before), 'Image archive changed during copy')
                require(size == before.st_size and copied.hexdigest() == expected_sha256, 'Copied image archive checksum mismatch')
            output.flush()
            os.fchown(output.fileno(), before.st_uid, before.st_gid)
            for name, value in attrs.items(): os.setxattr(output.fileno(), name, value)
            os.fchmod(output.fileno(), stat.S_IMODE(before.st_mode))
            os.utime(output.fileno(), ns=(before.st_atime_ns, before.st_mtime_ns))
            os.fsync(output.fileno())
        require(sha(temporary) == expected_sha256, 'Copied image archive readback mismatch')
        require(signature(source.stat()) == signature(before), 'Source image archive changed before publication')
        # The temporary and final name have the same parent/mount. link is an
        # exclusive publication: a concurrently created target is never replaced.
        os.link(temporary, target)
        parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(parent_fd)
        finally: os.close(parent_fd)
        return {'method': 'verified_copy_after_EXDEV', 'sha256': expected_sha256, 'bytes': before.st_size}
    finally:
        temporary.unlink(missing_ok=True)
