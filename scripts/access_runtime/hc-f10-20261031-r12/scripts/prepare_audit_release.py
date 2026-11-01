#!/usr/bin/env python3
"""Freeze this refactor for review. Never deploy, migrate, install units, or contact devices."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import sys

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'infra/backend'))
from backup_export import export_snapshot
from backup_protocol import atomic_json,sha256
from restore_runtime import environment

RELEASE='hc-refactor-20261026-r4'


def freeze(destination):
    destination=Path(destination)
    if destination.exists(): raise ValueError('Release destination already exists; never overwrite a frozen release')
    previous=BASE/'backups/releases/hc-sleeping-20261023-r2'
    destination.mkdir(mode=0o755,parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix='hc-release-source-') as temporary:
            snapshot=Path(temporary)/'source'
            export_snapshot(BASE,snapshot)
            shutil.copytree(snapshot,destination/'source')
        source=destination/'source'
        # This canonical replacement is inactive; the live original remains unchanged.
        exporter=source/'scripts/export_gitea_config_snapshot.sh'
        exporter.write_text('#!/usr/bin/env bash\nset -Eeuo pipefail\nBASE="${BASE:-/srv/docker/homecontrol}"\nexec python3 "$BASE/scripts/export_config_snapshot.py" "$@"\n')
        exporter.chmod(0o755)
        manifest=json.loads((source/'EXPORT_MANIFEST.json').read_text())
        for row in manifest['files']:
            row['sha256']=sha256(source/row['path'])
        atomic_json(source/'EXPORT_MANIFEST.json',manifest)
        private=destination/'private';private.mkdir(mode=0o700)
        runtime=private/'runtime/infra';runtime.mkdir(parents=True,mode=0o700)
        shutil.copy2(previous/'private/infra.env',runtime/'.env')
        environment(private/'runtime')
        # All application build dependencies are inherited from already pinned images.
        comparisons=[(source/'infra/backend/requirements.txt',previous/'source/backend/requirements.txt'),
                     (source/'infra/frontend/package-lock.json',previous/'source/frontend/package-lock.json'),
                     (source/'apps/hc_ingest/requirements.txt',BASE/'backups/releases/hc-combustion-feedback-20261025-r3/source/ingest/requirements.txt')]
        if any(sha256(a)!=sha256(b) for a,b in comparisons): raise ValueError('Cached dependency set differs; review before building')
        builds=destination/'builds';builds.mkdir()
        (builds/'backend.Dockerfile').write_text('FROM homecontrol-backend:hc-sleeping-20261023-r2\nCOPY *.py /app/\nCOPY static /app/static\n')
        (builds/'ingest.Dockerfile').write_text('FROM homecontrol-ingest:hc-combustion-feedback-20261025-r3\nCOPY mqtt_ingest_multi.py mqtt_flood_detector.py /app/\n')
        (builds/'frontend.Dockerfile').write_text('FROM hc-sleeping-frontend-build:20261023-r2 AS build\nWORKDIR /app\nCOPY . /app/\nRUN npm run test:mower && npm run test:ai && npm run test:backup && npm run build\nFROM nginx:1.27-alpine\nCOPY nginx.conf /etc/nginx/conf.d/default.conf\nCOPY --from=build /app/dist /usr/share/nginx/html\n')
        files={p.relative_to(source).as_posix():sha256(p) for p in sorted(source.rglob('*')) if p.is_file()}
        result=dict(release=RELEASE,state='prepared_not_deployed',source_sha256=files,
                    images={name:'homecontrol-'+name+':'+RELEASE for name in ('backend','frontend','ingest')},
                    previous_backend='homecontrol-backend:hc-sleeping-20261023-r2',
                    previous_frontend='homecontrol-frontend:hc-sleeping-20261023-r2',
                    previous_ingest='homecontrol-ingest:hc-combustion-feedback-20261025-r3',
                    migrations=['059','060','061'],baseline_on_existing_db=False,
                    audit_points=['HC-07','HC-17','HC-18','HC-19','HC-25','HC-27','HC-28','HC-29','HC-30','HC-31','HC-37','HC-38','HC-39','HC-42','HC-45','HC-46','HC-47'],
                    production_changed=False,physical_commands=False)
        atomic_json(destination/'release.json',result)
        return {key:result[key] for key in ('release','state','images','production_changed')}
    except Exception:
        # Keep the failed package private and visibly incomplete for inspection.
        destination.chmod(0o700)
        atomic_json(destination/'PREPARATION_FAILED.json',{'complete':False},0o600)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--destination',type=Path,default=BASE/'backups/releases'/RELEASE)
    args=parser.parse_args()
    if args.freeze: print(json.dumps(freeze(args.destination),indent=2))
    else: print(json.dumps(dict(release=RELEASE,destination=str(args.destination),action='plan',production_changed=False),indent=2))


if __name__=='__main__':main()
