#!/usr/bin/env python3
"""Plan by default. Explicit installation selects system scope and retires duplicate user timers."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import uuid

CODE=Path(__file__).resolve().parent
sys.path.insert(0,str(CODE.parent/'infra/backend'))
from backup_protocol import atomic_json, read_json
from backup_service import BackupService, validate_schedule_time
from deployment_policy import effective_backup_settings, public_status

USER_TIMERS=('homecontrol-backup.timer','homecontrol-log-maintenance.timer')
SERVICES=('homecontrol-backup.service','homecontrol-ai-weekly-backup.service',
          'homecontrol-full-ai-backup-request.service','homecontrol-restic-check.service','homecontrol-log-maintenance.service')


def unit_sources():
    return {p.name:p.read_text() for p in sorted((CODE/'systemd/f6').iterdir()) if p.suffix in ('.service','.timer','.path')}


def schedule_units(units,settings):
    settings=effective_backup_settings(settings)
    units=dict(units)
    daily=validate_schedule_time(settings['schedule_time'],'schedule_time')
    import re
    weekly=str(settings['ai_weekly_backup_schedule']).strip()
    if not re.fullmatch(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:[01]\d|2[0-3]):[0-5]\d',weekly):
        raise ValueError('Invalid weekly backup calendar')
    units['homecontrol-backup.timer']=re.sub(r'OnCalendar=.*','OnCalendar=*-*-* '+daily+':00',units['homecontrol-backup.timer'])
    units['homecontrol-ai-weekly-backup.timer']=re.sub(r'OnCalendar=.*','OnCalendar='+weekly+':00',units['homecontrol-ai-weekly-backup.timer'])
    enabled={'homecontrol-backup.timer':settings['schedule_enabled'],
             'homecontrol-ai-weekly-backup.timer':settings['ai_weekly_backup_enabled'],
             'homecontrol-restic-check.timer':settings['restic_enabled'],
             'homecontrol-log-maintenance.timer':True,
             'homecontrol-full-ai-backup-request.path':True,'homecontrol-backup-apply.path':True}
    return units,enabled


def assert_no_user_units():
    # A dead bus alone does not prove that a user's timers are disabled.
    locations=[Path('/etc/systemd/user'),Path('/usr/lib/systemd/user'),Path('/root/.config/systemd/user')]
    locations += [Path(row.pw_dir)/'.config/systemd/user' for row in pwd.getpwall()]
    for location in locations:
        for name in USER_TIMERS:
            if location.exists() and any(location.rglob(name)):
                raise RuntimeError('Fresh-host mode refuses existing user backup timer units; start that user manager and retire them explicitly')


def install(*,apply=False,unit_dir=Path('/etc/systemd/system'),root=Path('/srv/docker/homecontrol/backups'),
            legacy_user='a',wait_idle=False,run=subprocess.run,fresh_host=False,restore_host=False):
    root=Path(root);unit_dir=Path(unit_dir)
    stored=read_json(root/'backup_settings.json')
    if (root/'backup_settings.json').exists() and stored is None:
        raise ValueError('Invalid backup settings; no schedule changes made')
    settings={**BackupService.DEFAULT_SETTINGS,**(stored or {})}
    units,enabled=schedule_units(unit_sources(),settings)
    if restore_host:
        for name in ('homecontrol-post-boot-health.service','homecontrol-post-boot-health.timer'):
            units[name]=(CODE/'systemd'/name).read_text()
        enabled['homecontrol-post-boot-health.timer']=True
        units['homecontrol-backup-apply.service']=units['homecontrol-backup-apply.service'].replace('--apply --wait-idle','--apply --wait-idle --fresh-host --restore-host')
        for name in ('backup_runner.py','post_boot_health.sh','export_config_snapshot.py'):
            if not (CODE/name).is_file(): raise ValueError('Required restored host script is missing: '+name)

    plan=dict(scope='system',units={n:hashlib.sha256(v.encode()).hexdigest() for n,v in units.items()},
              enabled=enabled,retire_user=legacy_user,retire_user_timers=list(USER_TIMERS),applied=False)
    plan['deployment']=public_status()
    if not apply: return plan
    if os.geteuid()!=0: raise PermissionError('Explicit F6 installation requires root')
    def call(args,allowed=(0,)):
        result=run(args,capture_output=True,text=True)
        if result.returncode not in allowed: raise RuntimeError('Unit command failed: '+' '.join(args[:2]))
        return result
    user=None
    try:
        account=pwd.getpwnam(legacy_user)
        user=['runuser','-u',legacy_user,'--','env','XDG_RUNTIME_DIR=/run/user/'+str(account.pw_uid),
              'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(account.pw_uid)+'/bus','systemctl','--user']
        call(user+['show','homecontrol-backup.timer','--property=ActiveState','--no-pager'])
    except (KeyError,RuntimeError):
        if not fresh_host: raise
        assert_no_user_units()
        user=None
    handles=[]
    try:
        root.mkdir(parents=True,exist_ok=True)
        for name in ('ai-backup.lock','homecontrol-backup.lock'):
            handle=(root/name).open('a');handles.append(handle)
            fcntl.flock(handle,fcntl.LOCK_EX|(0 if wait_idle else fcntl.LOCK_NB))
        for prefix,services in ((['systemctl'],SERVICES),(user,('homecontrol-backup.service','homecontrol-log-maintenance.service'))):
            if prefix is None: continue
            for service in services:
                result=call(prefix+['is-active','--quiet',service],allowed=(0,3,4))
                if result.returncode==0: raise RuntimeError('A legacy backup/maintenance service is active; retry when idle')
        # A legacy apply helper must not overwrite the new files concurrently.
        # When invoked by our own apply unit, its MainPID is this installer.
        applying=call(['systemctl','is-active','--quiet','homecontrol-backup-apply.service'],allowed=(0,3,4))
        if applying.returncode==0:
            owner=call(['systemctl','show','homecontrol-backup-apply.service','--property=MainPID','--value']).stdout.strip()
            if owner!=str(os.getpid()): raise RuntimeError('A different unit installer is active; retry when idle')
        bundle=root/'f6-unit-rollback'/uuid.uuid4().hex;bundle.mkdir(parents=True,mode=0o700)
        previous={}
        for name in units:
            path=unit_dir/name
            if path.exists(): shutil.copy2(path,bundle/name)
            previous[name]=dict(existed=path.exists(),enabled=call(['systemctl','is-enabled',name],allowed=(0,1,3,4)).stdout.strip())
        previous['user_timers']={name:call(user+['is-enabled',name],allowed=(0,1,3,4)).stdout.strip() for name in USER_TIMERS} if user else {}
        atomic_json(bundle/'before.json',previous,0o600)
        try:
            # Disable old source watchers before replacing installed units. No source
            # under scripts/systemd/ is rewritten by this installer.
            call(['systemctl','stop','homecontrol-backup-apply.path'])
            if user:
                call(user+['disable','--now',*USER_TIMERS])
                call(user+['daemon-reload'])
            for name in enabled: call(['systemctl','stop',name])
            unit_dir.mkdir(parents=True,exist_ok=True)
            for name,text in units.items():
                path=unit_dir/name
                temporary=unit_dir/('.'+name+'.f6')
                temporary.write_text(text);temporary.chmod(0o644);os.replace(temporary,path)
            call(['systemctl','daemon-reload'])
            # Resume the apply watcher last; do not run a backup during installation.
            for name,wanted in enabled.items():
                call(['systemctl','enable' if wanted else 'disable','--now',name])
            for name in USER_TIMERS if user else ():
                result=call(user+['is-enabled',name],allowed=(0,1,3,4))
                if result.returncode==0: raise RuntimeError('Duplicate user timer remains enabled')
            for name,wanted in enabled.items():
                result=call(['systemctl','is-active','--quiet',name],allowed=(0,3,4))
                if (result.returncode==0)!=bool(wanted): raise RuntimeError('Installed unit active state differs from plan')
            if restore_host:
                triggers={}
                for name,wanted in enabled.items():
                    if wanted and name.endswith('.timer'):
                        value=call(['systemctl','show',name,'--property=NextElapseUSecRealtime,NextElapseUSecMonotonic','--no-pager']).stdout.strip()
                        if not any(line.partition('=')[2].strip() not in ('','0','infinity','n/a') for line in value.splitlines()):
                            raise RuntimeError('Restored timer has no next trigger: '+name)
                        triggers[name]=value
                plan['next_triggers']=triggers
            for name,text in units.items():
                if (unit_dir/name).read_text()!=text: raise RuntimeError('Installed unit version differs: '+name)

        except Exception:
            # Restore the saved installed bytes and enabled states on a failed
            # transition. No backup or file restore is started by this rollback.
            for name in enabled:
                run(['systemctl','stop',name],capture_output=True,text=True)
            for name in units:
                path=unit_dir/name
                if previous[name]['existed']: shutil.copy2(bundle/name,path)
                else: path.unlink(missing_ok=True)
            run(['systemctl','daemon-reload'],capture_output=True,text=True)
            for name in enabled:
                action='enable' if previous[name]['enabled'].startswith('enabled') else 'disable'
                run(['systemctl',action,'--now',name],capture_output=True,text=True)
            for name,state in previous['user_timers'].items():
                run(user+['enable' if state.startswith('enabled') else 'disable','--now',name],capture_output=True,text=True)
            atomic_json(bundle/'failed-transition.json',dict(rollback_attempted=True),0o600)
            raise
        plan.update(applied=True,rollback_bundle=str(bundle))
        atomic_json(root/'f6-installed.json',plan)
        return plan
    finally:
        for handle in reversed(handles):handle.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--wait-idle',action='store_true')
    parser.add_argument('--legacy-user',default='a')
    parser.add_argument('--fresh-host',action='store_true')
    parser.add_argument('--restore-host',action='store_true')
    args=parser.parse_args()
    print(json.dumps(install(apply=args.apply,legacy_user=args.legacy_user,wait_idle=args.wait_idle,fresh_host=args.fresh_host,restore_host=args.restore_host),indent=2))


if __name__=='__main__':main()
