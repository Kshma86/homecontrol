#!/usr/bin/env python3
"""Publish a consistent Home Assistant SQLite copy, including committed WAL data."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def snapshot(source_directory, target_directory):
    source = Path(source_directory)/'home-assistant_v2.db'
    target = Path(target_directory)/source.name
    if source.is_symlink() or target.is_symlink():
        raise ValueError('SQLite backup cannot follow symlinks')
    if not source.exists():
        return {'present': False}
    if not source.is_file() or not target.parent.is_dir():
        raise ValueError('Invalid SQLite backup path')
    for suffix in ('-wal', '-shm'):
        sidecar = target.with_name(target.name+suffix)
        if sidecar.is_symlink() or sidecar.exists() and not sidecar.is_file():
            raise ValueError('Invalid SQLite sidecar in staging')
    fd, name = tempfile.mkstemp(prefix='.ha-sqlite-', suffix='.db', dir=target.parent)
    temporary = Path(name)
    os.fchmod(fd, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as live:
            with closing(sqlite3.connect(temporary)) as copy:
                live.backup(copy)
                # Publish a standalone database, without inherited WAL mode or
                # an open connection that could later recreate sidecars.
                copy.execute('pragma journal_mode=delete')
                if copy.execute('pragma quick_check').fetchall() != [('ok',)]:
                    raise ValueError('Home Assistant SQLite copy failed integrity verification')
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        for suffix in ('-wal', '-shm'):
            target.with_name(target.name+suffix).unlink(missing_ok=True)
        os.replace(temporary, target)
        return {'present': True, 'consistent_online_copy': True, 'integrity': 'ok'}
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.source, args.target)))
