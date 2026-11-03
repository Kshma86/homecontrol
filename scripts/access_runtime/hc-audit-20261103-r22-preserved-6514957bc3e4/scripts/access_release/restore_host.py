#!/usr/bin/env python3
"""HC-45: install F6 base units and retain the access-release adapters."""
import argparse
import json
from pathlib import Path
import sys
from common import BASE, RUNTIME, units

LOCAL_SCRIPTS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RUNTIME/'scripts' if RUNTIME.exists() else LOCAL_SCRIPTS))
from install_backup_f6 import install


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if args.apply and not RUNTIME.exists():raise SystemExit('Installed access runtime required before apply')
    result=install(apply=args.apply,wait_idle=True,fresh_host=True,restore_host=True)
    if args.apply:
        from install import install_units
        install_units()
    result['access_units']=list(units(RUNTIME if RUNTIME.exists() else LOCAL_SCRIPTS.parent))
    result['access_runtime']=str(RUNTIME)
    print(json.dumps(result,indent=2))
