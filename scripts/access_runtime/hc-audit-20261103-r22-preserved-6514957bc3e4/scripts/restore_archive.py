#!/usr/bin/env python3
"""Strict archive/snapshot selection shared by the restore entry points."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'infra/backend'))
from backup_protocol import atomic_json, sha256, verify_archive
from backup_restore import archive_index, canonical, parent_fd

CANONICAL = '/srv/docker/homecontrol'


def snapshot(rows, requested='latest'):
    candidates = [row for row in rows if 'homecontrol' in (row.get('tags') or [])
                  and isinstance(row.get('id'), str) and len(row['id']) == 64
                  and all(c in '0123456789abcdef' for c in row['id'])]
    if requested != 'latest':
        candidates = [row for row in candidates if row['id'].startswith(requested)]
        if len(candidates) != 1: raise ValueError('Snapshot ID is missing or ambiguous in homecontrol tag')
    if not candidates: raise ValueError('No homecontrol snapshot')
    return max(candidates, key=lambda row: row.get('time', ''))['id']


def latest_archive(directory):
    root = Path(directory)
    candidates = [p for p in root.glob('homecontrol_*.tar.gz') if p.is_file() and not p.is_symlink()]
    if not candidates: raise ValueError('Restored snapshot contains no HomeControl archive')
    return max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name))


def prepare_database(archive_path, work_root):
    archive_path = Path(archive_path)
    with tarfile.open(archive_path, 'r:gz') as archive:
        index, _ = archive_index(archive)
        checked = verify_archive(archive_path)
        dumps = [(name, member) for name, member in index.items()
                 if name.startswith('postgres/') and name.endswith('.dump') and member.isfile()]
        if len(dumps) != 1: raise ValueError('Selected verified archive must contain exactly one PostgreSQL dump')
        name, member = dumps[0]
        if not member.size: raise ValueError('Empty database dump')
        Path(work_root).mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='selected-archive-', dir=work_root))
        stage.chmod(0o700)
        dump = stage/'database.dump'
        try:
            with archive.extractfile(member) as source, dump.open('xb') as target:
                shutil.copyfileobj(source, target)
                target.flush(); os.fsync(target.fileno())
            dump.chmod(0o600)
            result = dict(version=1, archive=str(archive_path.absolute()), archive_sha256=checked['sha256'],
                          member=name, dump=str(dump), dump_sha256=sha256(dump))
            atomic_json(stage/'selection.json', result, 0o600)
            return result
        except Exception:
            shutil.rmtree(stage)
            raise


def _secret_members(archive):
    result = []; names = set()
    for member in archive.getmembers():
        if member.name in ('.', './') and member.isdir(): continue
        name = canonical(member.name)
        if name in names: raise ValueError('Duplicate secret member')
        names.add(name)
        if not (member.isdir() or member.isfile()): raise ValueError('Secret bundle contains a link or special file')
        allowed = (name in ('SECRETS_BUNDLE_CONTENTS.txt','SECRETS_BUNDLE_METADATA.txt')
                   or name.startswith('srv/docker/homecontrol/') or name.startswith('etc/homecontrol/'))
        if member.isdir():
            allowed = allowed or any(prefix.startswith(name+'/') for prefix in ('srv/docker/homecontrol','etc/homecontrol')) or name in ('srv/docker/homecontrol','etc/homecontrol')
        if not allowed: raise ValueError('Secret bundle path outside the canonical allowlist')
        result.append((name, member))
    if not any(name=='SECRETS_BUNDLE_CONTENTS.txt' for name,_ in result): raise ValueError('Secret contents manifest missing')
    return result


def secrets(archive_path, target, apply=False):
    target = Path(target)
    if apply and target != Path('/'): raise ValueError('Secret apply root must be /')
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = _secret_members(archive)  # validate entire bundle before any write
        for name, member in members:
            if apply and name.startswith('SECRETS_BUNDLE_'): continue
            out = target/name
            # No extraction API and no archive ownership/suid restoration.
            with parent_fd(out, create=True) as (fd, leaf):
                if member.isdir():
                    try: os.mkdir(leaf, 0o700, dir_fd=fd)
                    except FileExistsError:
                        directory = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        os.close(directory)
                    continue
                temporary = '.hc-secret-'+os.urandom(12).hex()
                try:
                    output_fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=fd)
                    with os.fdopen(output_fd, 'wb') as output, archive.extractfile(member) as source:
                        shutil.copyfileobj(source, output)
                        # Secret files are private regardless of their old mode.
                        os.fchmod(output.fileno(), 0o600)
                        output.flush(); os.fsync(output.fileno())
                    os.replace(temporary, leaf, src_dir_fd=fd, dst_dir_fd=fd)
                    os.fsync(fd)
                finally:
                    try: os.unlink(temporary, dir_fd=fd)
                    except FileNotFoundError: pass
    return {'validated_files': sum(member.isfile() for _,member in members)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p=sub.add_parser('snapshot');p.add_argument('json_file');p.add_argument('--requested', default='latest')
    p=sub.add_parser('latest');p.add_argument('directory')
    p=sub.add_parser('verify');p.add_argument('archive')
    p=sub.add_parser('database');p.add_argument('archive');p.add_argument('work_root');p.add_argument('selection_file')
    p=sub.add_parser('secrets');p.add_argument('archive');p.add_argument('target');p.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.command=='snapshot': print(snapshot(json.loads(Path(args.json_file).read_text()), args.requested))
    elif args.command=='latest': print(latest_archive(args.directory))
    elif args.command=='verify':
        with tarfile.open(args.archive,'r:gz') as archive: archive_index(archive)
        print(json.dumps(verify_archive(args.archive)))
    elif args.command=='database': atomic_json(args.selection_file,prepare_database(args.archive,args.work_root),0o600)
    elif args.command=='secrets': print(json.dumps(secrets(args.archive,args.target,args.apply)))


if __name__=='__main__':
    try: main()
    except (OSError,ValueError,tarfile.TarError) as exc:
        raise SystemExit('Restore validation failed: '+str(exc))
