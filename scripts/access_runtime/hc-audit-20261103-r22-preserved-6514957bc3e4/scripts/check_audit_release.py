#!/usr/bin/env python3
"""Read-only integrity/Compose check for the prepared refactor release. Never applies it."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]/'backups/releases/hc-refactor-20261026-r4'


def main():
    manifest=json.loads((ROOT/'release.json').read_text())
    for path,key in (('private/runtime/infra/.env','private_env_sha256'),
                     ('private/homecontrol-secrets-prepared.tar.gz.age','encrypted_bundle_sha256')):
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=manifest[key]:
            raise RuntimeError('Prepared private artifact changed; values withheld')
    for name,digest in manifest['source_sha256'].items():
        if hashlib.sha256((ROOT/'source'/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Frozen source changed: '+name)
    for name,digest in manifest.get('package_sha256',{}).items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Release artifact changed: '+name)
    for name,expected in manifest['image_ids'].items():
        result=subprocess.run(['docker','image','inspect',name],capture_output=True,text=True,check=True)
        if json.loads(result.stdout)[0]['Id']!=expected:raise RuntimeError('Pinned image changed: '+name)
    compose=json.loads((ROOT/'compose-command.json').read_text())
    for mode in ('release','rollback'):
        result=subprocess.run(compose+['-f',str(ROOT/(mode+'.override.json')),'config','--format','json'],capture_output=True,text=True)
        if result.returncode:raise RuntimeError('Compose render failed; private values withheld')
        data=json.loads(result.stdout);services=data['services']
        if not services['backend']['environment']['DATABASE_URL'].startswith('postgresql://hc_app:'):raise RuntimeError('Wrong runtime role')
        if not services['backend']['environment']['SQL_LAB_DATABASE_URL'].startswith('postgresql://hc_lab:'):raise RuntimeError('Wrong reader role')
        if services['hc_ingest']['environment']['PG_USER']!='hc_app':raise RuntimeError('Wrong ingest role')
    print(json.dumps(dict(integrity_ok=True,compose_ok=True,production_changed=False,
                         ready_for_unconditional_deploy=False,remaining_checks=manifest['remaining_checks']),indent=2))


if __name__=='__main__':main()
