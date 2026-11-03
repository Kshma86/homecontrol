#!/usr/bin/env python3
"""HC-17/18 public exporter; the live legacy entrypoint is unchanged until cutover."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'infra/backend'))
from backup_export import export_snapshot, secrets_manifest, stage_snapshot

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', nargs='?', type=Path)
    parser.add_argument('--base', type=Path, default=Path(os.environ.get('BASE', '/srv/docker/homecontrol')))
    parser.add_argument('--secrets-manifest', type=Path)
    parser.add_argument('--stage-only', action='store_true')
    args = parser.parse_args()
    if args.stage_only:
        if not args.target:
            parser.error('--stage-only requires the dedicated export checkout')
        print(json.dumps(stage_snapshot(args.target)))
    elif args.secrets_manifest:
        secrets_manifest(args.base, args.secrets_manifest)
    elif args.target:
        print(json.dumps(export_snapshot(args.base, args.target)))
    else:
        parser.error('Snapshot target or --secrets-manifest is required')

if __name__ == '__main__':
    main()
