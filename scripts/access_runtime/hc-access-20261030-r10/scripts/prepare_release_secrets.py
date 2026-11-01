#!/usr/bin/env python3
"""Encrypt an inactive release's canonical secret bundle without changing live secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

BASE=Path(__file__).resolve().parents[1]
RELEASE=BASE/'backups/releases/hc-refactor-20261026-r4'
sys.path.insert(0,str(BASE/'infra/backend'))
from backup_export import secrets_manifest


def prepare(release=RELEASE):
    release=Path(release).resolve()
    if release.parent != (BASE/'backups/releases').resolve():
        raise ValueError('Secret preparation requires an inactive local release directory')
    private=release/'private';owner=release.stat()
    recipient=next(line.strip() for line in (BASE/'secrets/age-recipient.txt').read_text().splitlines()
                   if line.strip() and not line.startswith('#'))
    manifest=private/'secret-source-manifest.txt';secrets_manifest(BASE,manifest)
    paths=[]
    for line in manifest.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        path=Path(line) if line.startswith('/') else BASE/line
        if not (str(path).startswith(str(BASE)+'/') or str(path).startswith('/etc/homecontrol/')):
            raise ValueError('Secret manifest path outside allowed roots')
        paths.append(path)
    output=private/'homecontrol-secrets-prepared.tar.gz.age'
    if output.exists():raise ValueError('Prepared encrypted bundle already exists; refusing overwrite')
    copied=[];missing=[]
    try:
        with tempfile.TemporaryDirectory(prefix='.secret-stage-',dir=private) as temporary:
            stage=Path(temporary)
            for path in paths:
                source=private/'runtime/infra/.env' if path==BASE/'infra/.env' else path
                if not source.exists():missing.append(str(path));continue
                if source.is_symlink() or not source.is_file():raise ValueError('Secret source must be a regular file')
                target=stage/str(path).lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target);target.chmod(0o600);copied.append(str(path))
            (stage/'SECRETS_BUNDLE_CONTENTS.txt').write_text('\n'.join(copied)+'\n')
            (stage/'SECRETS_BUNDLE_METADATA.txt').write_text('release='+release.name+'\nprepared_not_deployed=true\n')
            process=subprocess.Popen(['age','-r',recipient,'-o',str(output)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                with tarfile.open(fileobj=process.stdin,mode='w|gz') as tar:tar.add(stage,arcname='.')
                process.stdin.close();process.stderr.read()
                if process.wait():raise RuntimeError('Encryption failed')
            finally:
                if process.poll() is None:process.kill();process.wait()
        output.chmod(0o600)
        report=dict(encrypted=True,copied_files=len(copied),missing_optional_paths=missing,
                    auth_variants_covered=sum('xiaomi_cloud_auth' in name for name in copied),
                    prepared_runtime_env_used=True,live_secret_files_changed=False,
                    sha256=hashlib.sha256(output.read_bytes()).hexdigest(),decryption_of_real_bundle_performed=False)
        report_path=release/'evidence/prepared-secret-bundle.json'
        report_path.write_text(json.dumps(report,indent=2)+'\n')
        for path in (manifest,output,report_path):
            if os.geteuid()==0:os.chown(path,owner.st_uid,owner.st_gid)
        return {key:report[key] for key in ('encrypted','copied_files','auth_variants_covered','prepared_runtime_env_used','live_secret_files_changed')}
    except Exception:
        output.unlink(missing_ok=True)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--release-directory',type=Path,default=RELEASE);args=parser.parse_args()
    try:print(json.dumps(prepare(args.release_directory) if args.prepare else {'action':'plan','production_changed':False}))
    except Exception as exc:raise SystemExit('Inactive secret bundle preparation failed ('+type(exc).__name__+'); no secret values displayed')
