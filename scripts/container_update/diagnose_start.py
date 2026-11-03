#!/usr/bin/env python3
"""Read-only, redacted diagnosis of the one-shot r23 launch; never resumes it."""
from datetime import datetime,timezone
import ast
import json
import os
from pathlib import Path
import re
import stat
import subprocess

BASE=Path('/srv/docker/homecontrol')
NAME='hc-containers-20261103-r23'
KIT=BASE/'backups/releases'/NAME
PRIVATE=KIT/'private'
CONDITIONS={
    'Release acceptance is incomplete':'acceptance_incomplete',
    'Acceptance report changed':'acceptance_report_changed',
    'Acceptance failed':'acceptance_failed',
    'Offline image archive changed':'offline_archive_changed',
    'Expected r22 baseline':'active_release_changed',
    'Active Compose changed':'compose_changed',
    'Existing hostops/MQTT guard is not active':'host_guard_inactive',
    'Existing backend is not ready':'backend_not_ready',
    'Robot must be idle or charging for the bridge handover':'robot_not_idle',
    'Active irrigation session':'irrigation_active',
    'Active backup/restore operation':'backup_active',
    'Active host job; reconcile first':'host_job_active',
    'Active backup or APT operation':'backup_or_apt_active',
    'Active hostops job':'host_job_active',
    'Insufficient filesystem reserve':'filesystem_reserve',
    'Insufficient runtime cache reserve':'runtime_cache_reserve',
    'MQTT access policy changed':'mqtt_policy_changed',
    'Missing MQTT access rules':'mqtt_rules_missing',
    'Zigbee bridge version differs':'zigbee_version',
    'MQTT read probe received no allowed message':'mqtt_probe_no_message',
    'Incomplete Zigbee identities':'zigbee_inventory',
    'Invalid Zigbee device inventory':'zigbee_inventory',
    'PostgreSQL version/collation mismatch':'postgres_version_or_collation',
    'Existing HA poller token is missing':'ha_credential_missing',
    'Home Assistant readiness failed':'ha_readiness',
    'HC runtime source drift':'r22_source_drift',
    'HC container identity changed':'r22_container_identity',
    'HC running state changed':'r22_running_state',
    'HC component unhealthy':'r22_health',
    'Other running containers require maintenance review':'other_container_running',
    'HC installed unit drift':'r22_unit_drift',
    'HC timer inactive or disabled':'r22_timer_inactive',
    'Expected reboot has not occurred':'host_reboot_check',
    'Expected kernel is not running':'host_kernel_check',
    'Expected HC bind mount missing':'backup_mount',
    'Installed package differs from reviewed plan':'host_package_version',
    'Health service failed during schedule acceptance':'health_service_failed',
    'Scheduled timer has no next trigger: homecontrol-post-boot-health.timer':'health_timer_trigger',
}
PREFIXES={'Sealed source changed: ':'sealed_source_changed',
          'Acceptance evidence changed: ':'sealed_evidence_changed',
          'Container changed since preparation: ':'container_identity_changed',
          'Command failed: ':'private_command_failed',
          'Private operation failed: ':'private_command_failed',
          'Release operation failed: ':'private_command_failed',
          'Backup unit changed: ':'scheduled_unit_changed',
          'Scheduled unit enablement differs: ':'scheduled_unit_enablement',
          'Scheduled unit active state differs: ':'scheduled_unit_active_state'}
ERRORS={'ValueError','RuntimeError','PermissionError','FileExistsError','FileNotFoundError',
        'KeyError','TypeError','AttributeError','ImportError','ModuleNotFoundError',
        'TimeoutError','JSONDecodeError','CalledProcessError','InterruptedError'}


def classify(value):
    if value in CONDITIONS:return CONDITIONS[value]
    return next((label for prefix,label in PREFIXES.items() if value.startswith(prefix)),'unrecognized')


def summarize(text):
    conditions=set();types=set();frames=[];last_command='none'
    for line in text.splitlines():
        match=re.match(r'^([A-Za-z]+Error): (.*)$',line)
        if match:
            kind,detail=match.groups()
            if kind in ERRORS:types.add(kind)
            label=classify(detail)
            if label!='unrecognized':conditions.add(label)
        if line.startswith('{'):
            try:row=json.loads(line)
            except ValueError:continue
            if isinstance(row,dict) and row.get('ok') is False:
                value=row.get('condition')
                if isinstance(value,str):
                    label=classify(value)
                    if label!='unrecognized':conditions.add(label)
        match=re.match(r'^\s*File "([^"\n]+)", line (\d+), in ([A-Za-z_]\w*|<module>)$',line)
        if match:
            file,number,function=match.groups();path=Path(file)
            allowed={'execute','verify','main','guard_runtime','platform_probes','firewall','bridge',
                     'call','adapter_call','snapshot','verify_package','verify_runtime_schedules',
                     'read','load','ha_ready','postgres_ready','active','idle','space_guard','check',
                     'read_bytes','open','digest','sha','<module>'}
            if path.name in {'activate.py','deploy.py','check.py','execute.py','backup_helper.py','pathlib.py','schedules.py','timer_settle.py'}:
                frames.append({'file':path.name,'line':int(number),'function':function if function in allowed else 'withheld'})
        if line.startswith('COMMAND '):
            try:args=ast.literal_eval(line[8:])
            except (ValueError,SyntaxError):continue
            if not isinstance(args,list) or not all(isinstance(a,str) for a in args):continue
            if args==['/usr/bin/python3',str(BASE/'maintenance/host-update-20261103/source/check.py'),'postcheck']:last_command='r22_host_postcheck'
            elif args[:2]==['docker','inspect']:last_command='docker_inspect'
            elif args[:2]==['docker','exec']:
                if args[-2:]==['--topic','zigbee/bridge/devices']:last_command='zigbee_bridge_devices_read'
                elif args[-2:]==['--topic','zigbee/bridge/info']:last_command='zigbee_bridge_info_read'
                else:last_command='container_probe'
            elif args and args[0]=='nft':last_command='firewall_read'
            elif args and args[0]=='systemctl':last_command='systemd'
            else:last_command='other_private_command'
    return {'conditions':sorted(conditions),'error_types':sorted(types),
            'last_command_kind':last_command,'traceback_frames':frames[-10:],'raw_detail_withheld':True}


def private_bytes(path,limit):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Protected path is a symlink')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o077:
            raise ValueError('Private input metadata is not trusted')
        if info.st_size>limit:stream.seek(-limit,os.SEEK_END)
        return stream.read(limit),info.st_size>limit


def main():
    if os.geteuid()!=0:raise PermissionError('Run this read-only diagnosis with local sudo')
    report={'release':NAME,'read_only':True,'deployment_performed':False,'remote_commands':0,
            'checked_at':datetime.now(timezone.utc).isoformat()}
    marker=json.loads((BASE/'infra/access-release.json').read_text())
    report['active_release']=marker.get('release') if marker.get('release') in (NAME,'hc-audit-20261103-r22') else 'other'
    report['private_entries_present']={name:(PRIVATE/name).exists() for name in
        ('activation-attempt.json','activation-error.json','activation-private.log','progress.json',
         'paused-units.json','pre-proof.json','post-proof.json','runtime','transition')}
    report['new_runtime_exists']=(BASE/'scripts/access_runtime'/NAME).exists()
    report['new_private_exists']=(BASE/'infra/ssh'/NAME).exists()
    if (PRIVATE/'activation-error.json').exists():
        raw,_=private_bytes(PRIVATE/'activation-error.json',16384);row=json.loads(raw)
        report['recorded_error_type']=row.get('error_type') if row.get('error_type') in ERRORS else 'withheld'
        phase=row.get('phase');report['recorded_phase']=phase if phase in ('starting','full_existing_repository_check','prepare_new_private_runtime','pre_full_backup','pre_router_pg_restore','post_full_backup','post_router_pg_restore') else 'other'
    if (PRIVATE/'activation-private.log').exists():
        raw,truncated=private_bytes(PRIVATE/'activation-private.log',2*1024**2)
        report['private_log']=dict(summarize(raw.decode(errors='replace')),tail_only=truncated)
    unit=subprocess.run(['systemctl','show','homecontrol-r23-container-update.service',
        '--property=ActiveState,SubState,MainPID','--no-pager'],capture_output=True,text=True,timeout=10)
    values=dict(line.split('=',1) for line in unit.stdout.splitlines() if '=' in line)
    report['worker_active']=values.get('ActiveState') in ('active','activating','deactivating') or values.get('MainPID','0')!='0'
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
