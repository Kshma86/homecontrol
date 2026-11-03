#!/usr/bin/env python3
"""Create and verify the final offline images, including every r22 rollback image."""
import gzip
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path('/srv/docker/homecontrol')
KIT=ROOT/'backups/releases/hc-containers-20261103-r23'
WORK=ROOT/'maintenance/container-update-20261103'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-existing',action='store_true');args=parser.parse_args()
    m=json.loads((KIT/'release.json').read_text())
    old=json.loads((ROOT/'backups/releases/hc-audit-20261103-r22/release.json').read_text())
    images=sorted(set(old['recovery_images'])|set(m['images'].values())|{r['image'] for r in m['baseline'].values()})
    archive=KIT/'private/access-images.tar.gz';temporary=archive.with_name('final-images.tar.gz')
    if args.verify_existing:
        if not temporary.is_file() or temporary.is_symlink():raise ValueError('Expected completed export')
    else:
        if temporary.exists():raise ValueError('Unreviewed partial archive')
        with temporary.open('xb') as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as compressed:
                with subprocess.Popen(['docker','save',*images],stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
                    shutil.copyfileobj(process.stdout,compressed,1024**2)
                    if process.wait():raise RuntimeError('Image export failed')
            raw.flush();os.fsync(raw.fileno())
    blobs=0;members=0;manifest=None;index=None;seen=set()
    with tarfile.open(temporary,'r|gz') as tar:
        for row in tar:
            if row.name in seen:raise ValueError('Duplicate archive entry')
            seen.add(row.name)
            if not row.isfile():
                if not row.isdir():raise ValueError('Unexpected archive link')
                continue
            members+=1;stream=tar.extractfile(row)
            if row.name=='manifest.json':manifest=json.load(stream)
            elif row.name=='index.json':index=json.load(stream)
            elif row.name.startswith('blobs/sha256/'):
                h=hashlib.sha256()
                for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
                if h.hexdigest()!=row.name.rsplit('/',1)[1]:raise ValueError('Image blob mismatch')
                blobs+=1
    if manifest is None:raise ValueError('Missing Docker manifest')
    # Docker 29 IDs identify OCI manifests/indexes, rather than image config blobs.
    descriptors={r['digest'] for r in index['manifests']} if index else set()
    if descriptors!=set(images) or any('blobs/sha256/'+image.split(':')[1] not in seen for image in images):
        raise ValueError('Offline recovery descriptor inventory differs')
    proof={'ok':True,'sha256':sha(temporary),'size_bytes':temporary.stat().st_size,
        'images':images,'image_count':len(images),'content_addressed_blobs_verified':blobs,
        'regular_members':members,'all_r22_baseline_images_included':True,'deployment_performed':False}
    previous=archive.with_name('intermediate-six-image-access-images.tar.gz')
    if archive.exists():
        if previous.exists():raise ValueError('Previous archive already preserved')
        os.rename(archive,previous)
    os.rename(temporary,archive)
    (WORK/'offline-archive-verification-final.json').write_text(json.dumps(proof,indent=2)+'\n')
    m['recovery_images']=images;m['offline_image_archive_sha256']=proof['sha256']
    (KIT/'release.json').write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k!='images'}))


if __name__=='__main__':main()
