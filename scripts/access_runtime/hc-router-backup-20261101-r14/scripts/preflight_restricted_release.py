#!/usr/bin/env python3
"""Read-only existing-host preflight for the AI-offline handover; never applies it."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen
sys.dont_write_bytecode=True

from check_restricted_release import check, RELEASE

BASE=Path(__file__).resolve().parents[1]
SERVICES=('homecontrol-backup.service','homecontrol-ai-weekly-backup.service',
          'homecontrol-restic-check.service','homecontrol-full-ai-backup-request.service',
          'homecontrol-log-maintenance.service','homecontrol-backup-apply.service')

def local_json(path):
    with urlopen('http://127.0.0.1:5000'+path,timeout=15) as response:return json.load(response)

def main():
    result=check();health=local_json('/health')
    if not health.get('db_ok') or not health.get('mqtt_ok'):raise RuntimeError('Production DB/MQTT health is not ready')
    data=local_json('/api/power-wall/state')
    row=next(row for row in data['devices'] if str(row['entity_id'])=='121')
    policy=json.loads((RELEASE/'source/infra/backend/deployment_policy.json').read_text())
    if (row['platform']!='tuya' or row['ext_id'] not in policy['blocked_tuya_device_ids']
            or 'homecontrol/cmd/tuya/'+row['entity_name']+'/switch' not in policy['blocked_command_topics']):
        raise RuntimeError('Live AI socket identity differs from the frozen policy')
    bindings=local_json('/api/process-bindings')['bindings']
    if isinstance(bindings,dict):bindings=bindings.values()
    binding=next(row for row in bindings if row['process_key']=='ai_node_power_plug')
    if str(binding['selected_entity_id'])!='121':raise RuntimeError('AI binding differs from the frozen policy')
    states={};active=[]
    for service in SERVICES:
        output=subprocess.run(['systemctl','show',service,'--property=ActiveState,SubState,MainPID','--no-pager'],capture_output=True,text=True,check=True)
        fields=dict(line.split('=',1) for line in output.stdout.splitlines() if '=' in line)
        states[service]=fields
        if fields.get('MainPID') not in ('','0',None) or fields.get('ActiveState') in ('active','activating','deactivating'):active.append(service)
    sys.path.insert(0,str(BASE/'infra/backend'))
    from backup_restore import recoveries
    pending_restore=recoveries(BASE/'restore_staging')
    names=['homecontrol-backend','homecontrol-frontend','homecontrol-ingest','homecontrol-tuya-poller',
           'homecontrol-postgres','homecontrol-mqtt','homecontrol-pgbouncer']
    rows=json.loads(subprocess.check_output(['docker','inspect',*names]))
    manifest=json.loads((RELEASE/'release.json').read_text())
    backend=next(row for row in rows if row['Name']=='/homecontrol-backend')
    previous=manifest['image_ids'][manifest['previous_backend']]
    allowed={previous,manifest['image_ids'][manifest['images']['backend']],manifest['image_ids'][manifest['rollback_image']]}
    if backend['Image'] not in allowed:raise RuntimeError('A newer live backend requires another baseline review')
    for name,expected in manifest.get('preserved_live_sources',{}).items():
        code="import hashlib;print(hashlib.sha256(open('/app/"+name+"','rb').read()).hexdigest())"
        actual=subprocess.check_output(['docker','exec','homecontrol-backend','python','-c',code],text=True).strip()
        if actual!=expected:raise RuntimeError('Live safety baseline changed; reprepare before deployment')
    containers=[dict(name=row['Name'],id=row['Id'],image=row['Image'],started_at=row['State']['StartedAt']) for row in rows]
    settings=BASE/'backups/backup_settings.json'
    return dict(package_integrity_ok=True,profile='ai-offline',live_health=health,
                pinned_ai_identity_matches=True,active_host_jobs=active,host_service_states=states,
                pending_restore_count=len(pending_restore),containers=containers,
                legacy_ai_request_marker_present=(BASE/'backups/full-ai-backup.request').exists(),
                backup_settings_sha256=hashlib.sha256(settings.read_bytes()).hexdigest(),
                free_bytes=shutil.disk_usage(BASE).free,
                can_prepare_existing_host_handover=not active and not pending_restore,
                fresh_private_pre_cutover_backup_required=True,privileged_unit_installation_required=True,
                explicit_deployment_instruction_required=True,
                production_changed=False,ai_connections_attempted=False,
                deferred_checks=result['deferred_checks'],remaining_checks=result['remaining_checks'])

if __name__=='__main__':
    try:print(json.dumps(main(),indent=2))
    except Exception as exc:raise SystemExit('Restricted preflight failed ('+type(exc).__name__+'); no private values displayed')
