#!/usr/bin/env python3
"""Only the common host runner's workers call this protocol adapter."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'infra/backend'))
from backup_protocol import atomic_json, now, publish, read_json, retention, seal, target

LOCAL_KEYS=('include_postgres','include_apps','include_infra','include_zigbee2mqtt',
            'include_homeassistant','include_scripts','include_docker_meta')

def main():
    root=Path(os.environ['BACKUP_ROOT']);run_id=os.environ['HC_BACKUP_RUN_ID']
    action=sys.argv[1]
    if action=='target': target(root,run_id,*sys.argv[2:])
    elif action=='ai-state':
        atomic_json(root/'ai-backup-state.json',dict(state=sys.argv[2],detail=sys.argv[3],updated_at=now(),run_id=run_id))
    elif action=='seal':
        settings=read_json(os.environ['HC_BACKUP_SETTINGS_FILE'])
        coverage={k:settings[k] for k in LOCAL_KEYS}
        seal(sys.argv[2],os.environ['HC_BACKUP_MODE'],coverage)
    elif action=='publish':
        settings=read_json(os.environ['HC_BACKUP_SETTINGS_FILE'])
        coverage={k:settings[k] for k in LOCAL_KEYS}
        receipt=publish(root,run_id,sys.argv[2],sys.argv[3],os.environ['HC_BACKUP_MODE'],coverage)
        # Retention follows verified publication only, never a failed/in-progress tar.
        retention(root,settings['retention_days'],receipt['name'])
    else: raise ValueError('Unknown backup protocol action')


if __name__=='__main__': main()
