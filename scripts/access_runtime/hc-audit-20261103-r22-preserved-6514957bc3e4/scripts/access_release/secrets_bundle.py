#!/usr/bin/env python3
"""Merge the canonical encrypted base bundle with current/access secrets, privately."""
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

from common import BASE, NAME, PRIVATE, digest, write_json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from restore_archive import secrets as extract_secrets


def prepare(kit):
    kit=Path(kit);private=kit/'private'
    original=BASE/'backups/releases/hc-refactor-ai-offline-20261027-r6/private/homecontrol-secrets-prepared.tar.gz.age'
    identity=BASE/'infra/ssh/homecontrol-secrets-age-key.txt'
    recipient=(BASE/'secrets/age-recipient.txt').read_text().strip()
    output=private/'homecontrol-secrets-access.tar.gz.age'
    if output.exists():raise ValueError('Refusing to overwrite the prepared encrypted bundle')
    with tempfile.TemporaryDirectory(prefix='.access-secrets-',dir=private) as folder:
        work=Path(folder);plain=work/'base.tar.gz'
        with plain.open('wb') as stream:
            process=subprocess.run(['age','-d','-i',str(identity),str(original)],stdout=stream,stderr=subprocess.PIPE)
        if process.returncode:raise RuntimeError('Base bundle decryption failed')
        root=work/'root';extract_secrets(plain,root)
        original_manifest=(BASE/'secrets/manifest.txt').read_text().splitlines()
        paths=[Path(line.strip()) if line.startswith('/') else BASE/line.strip() for line in original_manifest if line.strip() and not line.startswith('#')]
        paths.extend((BASE/'apps/xiaomi-x10/x10_maps').glob('xiaomi_cloud_auth*'))
        paths.extend(p for p in (BASE/'infra/ssh').iterdir() if p.is_file() and p!=identity)
        refreshed=[];inherited=[]
        for source in sorted(set(paths)):
            target=root/str(source).lstrip('/')
            try:
                if not source.is_file() or source.is_symlink():continue
                contents=source.read_bytes()
            except PermissionError:
                # A disposable reader gets this one file read-only, no network,
                # host socket or broad filesystem. Values travel only in a pipe.
                process=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
                    '--mount','type=bind,source='+str(source)+',target=/input,readonly',
                    '--entrypoint','cat','homecontrol-backend:hc-read-models-20261028-r8','/input'],capture_output=True)
                if process.returncode:
                    if target.is_file():inherited.append(str(source));continue
                    raise RuntimeError('Required secret cannot be snapshotted')
                contents=process.stdout
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(contents);target.chmod(0o600);refreshed.append(str(source))
        for source in (private/'runtime').rglob('*'):
            if not source.is_file() or source.is_relative_to(private/'runtime/images'):continue
            target=root/str(PRIVATE).lstrip('/')/source.relative_to(private/'runtime')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);target.chmod(0o600)
        files=[p for p in root.rglob('*') if p.is_file() and not p.name.startswith('SECRETS_BUNDLE_')]
        (root/'SECRETS_BUNDLE_CONTENTS.txt').write_text('\n'.join('/'+str(p.relative_to(root)) for p in sorted(files))+'\n')
        (root/'SECRETS_BUNDLE_METADATA.txt').write_text('release='+NAME+'\nprepared_not_deployed=true\n')
        process=subprocess.Popen(['age','-r',recipient,'-o',str(output)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdin,mode='w|gz') as tar:tar.add(root,arcname='.')
        process.stdin.close();process.stderr.read()
        if process.wait():raise RuntimeError('Access secret encryption failed')
        output.chmod(0o600)
        # Real encrypted bundle roundtrip in a private temporary tree, not live /.
        decrypted=work/'roundtrip.tar.gz'
        with decrypted.open('wb') as stream:
            p=subprocess.run(['age','-d','-i',str(identity),str(output)],stdout=stream,stderr=subprocess.PIPE)
        if p.returncode:raise RuntimeError('Prepared secret bundle cannot be decrypted')
        restored=work/'roundtrip';extract_secrets(decrypted,restored)
        for file in files:
            if digest(file)!=digest(restored/file.relative_to(root)):raise RuntimeError('Secret roundtrip checksum mismatch')
        report=dict(encrypted=True,roundtrip_verified=True,secret_files=len(files),current_files_refreshed=len(refreshed),
            inherited_protected_paths=inherited,includes_mqtt_credentials=True,includes_runtime_environments=True,
            images_excluded=True,live_secrets_changed=False,sha256=digest(output))
    write_json(kit/'evidence/secret-roundtrip.json',report,0o644)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--kit',type=Path,default=BASE/'backups/releases'/NAME)
    args=parser.parse_args()
    try:print(json.dumps(prepare(args.kit)))
    except Exception as exc:raise SystemExit('Private secret preparation failed ('+type(exc).__name__+'); no values displayed')
