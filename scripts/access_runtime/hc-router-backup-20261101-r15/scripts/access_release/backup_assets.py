#!/usr/bin/env python3
"""Include the exact offline access runtime and private job journal before sealing."""
import argparse
import json
from pathlib import Path
import shutil
import os
from common import BASE, NAME, PRIVATE, digest

JOURNAL=Path('/var/lib/homecontrol-hostops/jobs')
SETTINGS=BASE/'backups/backup_settings.json'


def collect(archive_root):
    archive_root=Path(archive_root)
    private=Path(os.environ.get('HC_ACCESS_PRIVATE',str(PRIVATE)))
    info=json.loads((private/'images/manifest.json').read_text())
    image=private/'images'/info['archive']
    if digest(image)!=info['sha256']:raise ValueError('Offline recovery image cache checksum failed')
    target=archive_root/'scripts/access_runtime'/NAME/'images';target.mkdir(parents=True,exist_ok=True)
    for name in (info['archive'],'manifest.json'):shutil.copyfile(private/'images'/name,target/name)
    if SETTINGS.exists():
        if SETTINGS.is_symlink() or not SETTINGS.is_file():raise ValueError('Invalid backup settings source')
        if not isinstance(json.loads(SETTINGS.read_text()),dict):raise ValueError('Invalid backup settings JSON')
        target=archive_root/'backups/backup_settings.json';target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(SETTINGS,target);target.chmod(0o600)
    journal=JOURNAL
    if journal.exists():
        target=archive_root/'infra/ssh'/NAME/'host-jobs';target.mkdir(parents=True,exist_ok=True)
        for source in journal.glob('*.json'):
            if source.is_symlink() or not source.is_file():raise ValueError('Unexpected host journal entry')
            value=json.loads(source.read_text())
            if value.get('state') in ('queued','running'):
                value.update(state='uncertain',error='backup snapshot; reconcile after restore')
            (target/source.name).write_text(json.dumps(value)+'\n');(target/source.name).chmod(0o600)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive_root',type=Path);args=parser.parse_args()
    collect(args.archive_root)
