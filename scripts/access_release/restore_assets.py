#!/usr/bin/env python3
"""Stage verified r10 recovery assets before any canonical file or DB replacement."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from common import BASE, NAME, PRIVATE, RUNTIME, QUIESCE, digest, no_symlinks, write_json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'infra/backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup_protocol import verify_archive
from backup_restore import archive_index

HA_IMAGE = 'ghcr.io/home-assistant/home-assistant:stable'


def recovery_aliases(index, archive, images):
    """Recover the HA tag from checksum-verified Docker metadata, never the network."""
    compose = index.get('homeassistant/docker-compose.yml')
    if compose is None:
        return {}
    if not compose.isfile() or compose.size > 1024 * 1024:
        raise ValueError('Invalid archived Home Assistant Compose')
    text = archive.extractfile(compose).read().decode()
    references = re.findall(r'^\s*image:\s*["\']?([^\s"\']+)["\']?\s*$', text, re.M)
    if len(references) != 1:
        raise ValueError('Home Assistant recovery requires one explicit image')
    if re.fullmatch(r'sha256:[0-9a-f]{64}', references[0]):
        if references[0] not in images:
            raise ValueError('Pinned Home Assistant image is absent from the offline cache')
        return {}
    if not re.search(r'^\s*image:\s*[\"\']?' + re.escape(HA_IMAGE) + r'[\"\']?\s*$', text, re.M):
        raise ValueError('Unsupported Home Assistant recovery image')
    metadata = index.get('docker_images.txt')
    if metadata is None or not metadata.isfile() or metadata.size > 4 * 1024 * 1024:
        raise ValueError('Missing archived Docker image metadata for Home Assistant')
    aliases = set()
    for line in archive.extractfile(metadata).read().decode().splitlines():
        parts = line.split()
        identifier = (parts[1] if len(parts) >= 2 and parts[0] == HA_IMAGE else
                      parts[2] if len(parts) >= 3 and parts[:2] == ['ghcr.io/home-assistant/home-assistant', 'stable'] else None)
        if identifier is not None:
            if not re.fullmatch(r'[0-9a-f]{12,64}', identifier):
                raise ValueError('Invalid archived Home Assistant image ID')
            aliases.update(image for image in images if image.startswith('sha256:' + identifier))
    if len(aliases) != 1:
        raise ValueError('Home Assistant image is missing or ambiguous in the offline cache')
    return {HA_IMAGE: aliases.pop()}


def stage_assets(archive_path, work, base=BASE):
    checked=verify_archive(archive_path)
    with tarfile.open(archive_path) as archive:
        index,_=archive_index(archive)
        def read_json(name):
            member=index[name]
            if not member.isfile() or member.size>1024*1024:raise ValueError('Invalid recovery metadata')
            return json.load(archive.extractfile(member))
        marker=read_json('infra/access-release.json')
        if marker['release']!=NAME:raise ValueError('Wrong recovery release')
        prefix='scripts/access_runtime/'+NAME+'/images/'
        info=read_json(prefix+'manifest.json')
        if info['archive']!='access-images.tar.gz' or info['sha256']!=marker['image_archive_sha256']:
            raise ValueError('Image cache and selected archive marker differ')
        model=read_json('scripts/access_runtime/'+NAME+'/runtime.compose.json')
        postgres=model['services']['postgres']['image']
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',postgres) or postgres not in info['images']:
            raise ValueError('Missing pinned PostgreSQL recovery image')
        aliases = recovery_aliases(index, archive, info['images'])
        work=Path(work);work.mkdir(parents=True,exist_ok=True)
        root=Path(tempfile.mkdtemp(prefix='access-assets-',dir=work));root.chmod(0o700)
        names={prefix+'manifest.json':'images/manifest.json',prefix+info['archive']:'images/'+info['archive']}
        if 'backups/backup_settings.json' in index:
            settings=read_json('backups/backup_settings.json')
            if not isinstance(settings,dict):raise ValueError('Invalid restored backup settings')
            from install_backup_f6 import BackupService, schedule_units, unit_sources
            schedule_units(unit_sources(),{**BackupService.DEFAULT_SETTINGS,**settings})
            names['backups/backup_settings.json']='backup-settings.json'
        jobs='infra/ssh/'+NAME+'/host-jobs/'
        for name in index:
            if name.startswith(jobs) and not index[name].isdir():
                tail=name[len(jobs):]
                if not re.fullmatch(r'[0-9a-f]{32}\.json',tail):raise ValueError('Unexpected recovered job')
                names[name]='host-jobs/'+tail
        hashes={}
        for name,relative in names.items():
            member=index[name]
            if not member.isfile():raise ValueError('Recovery assets must be regular files')
            out=root/relative;out.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as src,out.open('xb') as dst:shutil.copyfileobj(src,dst)
            out.chmod(0o600);hashes[relative]=digest(out)
        if hashes['images/'+info['archive']]!=info['sha256']:raise ValueError('Corrupt recovery image cache')
    # Preserve only previously root-owned, explicitly recorded table ownership.
    previous_owned=False
    old_marker=Path(base)/'infra/access-release.json';old_policy=Path(base)/'infra/ssh'/NAME/'network-policy.json'
    if old_marker.exists() and old_policy.exists():
        no_symlinks(old_marker);no_symlinks(old_policy)
        previous_owned=(json.loads(old_marker.read_text()).get('release')==NAME and
                        json.loads(old_policy.read_text()).get('owned_chain') is True and old_policy.stat().st_uid==0)
    manifest=root/'staged.json'
    write_json(manifest,dict(archive_sha256=checked['sha256'],files=hashes,
        postgres_image=postgres,image_aliases=aliases,previous_owned=previous_owned))
    return manifest


def checked_stage(manifest):
    manifest=Path(manifest);no_symlinks(manifest);value=json.loads(manifest.read_text())
    for relative,sha in value['files'].items():
        if relative not in ('images/manifest.json','images/access-images.tar.gz','backup-settings.json') and not re.fullmatch(r'host-jobs/[0-9a-f]{32}\.json',relative):
            raise ValueError('Invalid staged asset path')
        path=manifest.parent/relative;no_symlinks(path)
        if digest(path)!=sha:raise ValueError('Staged recovery assets changed')
    images = json.loads((manifest.parent/'images/manifest.json').read_text())['images']
    for alias,image in value.get('image_aliases', {}).items():
        if alias != HA_IMAGE or image not in images or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('Invalid offline recovery image alias')
    return manifest.parent,value


def quiesce(manifest):
    checked_stage(manifest)
    def run(*args):return subprocess.run(['systemctl',*args],capture_output=True,text=True)
    active=[n for n in QUIESCE if run('is-active','--quiet',n).returncode==0]
    try:
        for name in active:subprocess.run(['systemctl','stop',name],check=True)
        for name in ('homecontrol-backup.service','homecontrol-ai-weekly-backup.service',
                     'homecontrol-full-ai-backup-request.service','homecontrol-restic-check.service',
                     'homecontrol-log-maintenance.service','homecontrol-backup-apply.service'):
            if run('is-active','--quiet',name).returncode==0:raise ValueError('Running host operation; reconcile before full restore')
        for path in Path('/var/lib/homecontrol-hostops/jobs').glob('*.json'):
            if json.loads(path.read_text()).get('state') in ('queued','running'):raise ValueError('Running host job blocks full restore')
        for name in ('ai-backup.lock','homecontrol-backup.lock'):
            path=BASE/'backups'/name
            if path.exists():
                no_symlinks(path)
                with path.open('a') as handle:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if Path('/etc/systemd/system/homecontrol-hostops.service').exists():
            subprocess.run(['systemctl','stop','homecontrol-hostops.service'],check=True)
    except Exception:
        for name in active:run('start',name)
        raise


def apply_assets(manifest):
    root,value=checked_stage(manifest)
    for relative in value['files']:
        target=(BASE/'backups/backup_settings.json' if relative=='backup-settings.json' else
                RUNTIME/relative if relative.startswith('images/') else PRIVATE/relative)
        no_symlinks(target);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/relative,target);target.chmod(0o600)
    if value['previous_owned']:
        policy=PRIVATE/'network-policy.json';data=json.loads(policy.read_text())
        data['owned_chain']=True;write_json(policy,data)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage','load','apply','quiesce'))
    parser.add_argument('--archive',type=Path);parser.add_argument('--work',type=Path);parser.add_argument('--manifest',type=Path)
    args=parser.parse_args()
    if args.action=='stage':print(stage_assets(args.archive,args.work))
    else:
        if os.geteuid()!=0:raise SystemExit('Explicit root restore operation required')
        root,value=checked_stage(args.manifest)
        if args.action=='load':
            subprocess.run(['docker','load','-i',str(root/'images/access-images.tar.gz')],check=True,stdout=subprocess.DEVNULL)
            for alias,image in value.get('image_aliases', {}).items():
                subprocess.run(['docker','tag',image,alias],check=True,stdout=subprocess.DEVNULL)
            print(value['postgres_image'])
        elif args.action=='apply':apply_assets(args.manifest)
        else:quiesce(args.manifest)
