#!/usr/bin/env python3
"""Fixed worker admission; exit before any remote command in restricted releases."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'infra/backend'))
from deployment_policy import ai_disabled, backup_mode_allowed, MESSAGE

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--worker-mode',choices=('local','weekly','git','check','maintenance'))
    group.add_argument('--restricted',action='store_true')
    args=parser.parse_args()
    if args.restricted:
        return 0 if ai_disabled() else 1
    if not backup_mode_allowed(args.worker_mode):
        print(MESSAGE,file=sys.stderr)
        return 78
    return 0

if __name__=='__main__':raise SystemExit(main())
