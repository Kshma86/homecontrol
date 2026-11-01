#!/usr/bin/env python3
"""Development host executor, including router FTP. Canonical live entry is unchanged."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import uuid

CODE = Path(__file__).resolve().parent
sys.path.insert(0,str(CODE.parent/'infra/backend'))
from backup_protocol import MODES, RUN_ID, atomic_json, now, read_json, target
from backup_service import BackupService
from ai_power_coordination import AiPowerCoordinator
from deployment_policy import (backup_mode_allowed, effective_backup_settings, ai_disabled,
                               public_status, MESSAGE as RESTRICTION_MESSAGE)
from router_backup import is_router, validate as validate_router, repository as router_repository


WORKERS = {'local':'backup_archive_worker.sh','weekly':'backup_weekly_worker.sh',
           'git':'backup_config_sync_worker.sh',
           'check':'backup_check_worker.sh','maintenance':'backup_maintenance_worker.sh'}


def required_targets(mode, settings):
    git_targets = (['gitea_origin'] if settings.get('git_origin_enabled', True) else []) + (['git_offsite'] if settings['git_offsite_enabled'] else [])
    if mode=='git': return git_targets or ['git_offsite']
    if mode=='maintenance': return ['maintenance']
    if mode=='check': return ['restic_check'] if settings['restic_enabled'] else []
    targets=['local_archive']
    if mode=='weekly' or settings['restic_required']: targets.append('restic')
    if mode=='weekly':
        if is_router(settings): targets.append('secrets_bundle')
        else: targets.append('gitea_dump')
        if settings['git_enabled']:
            targets.extend(git_targets or ['git_offsite'])
    return targets


def _execute(root, mode, *, source='timer', run_id=None, wait=False, message=''):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if mode not in MODES: raise ValueError('Invalid backup mode')
    run_id=run_id or uuid.uuid4().hex
    if not RUN_ID.fullmatch(run_id): raise ValueError('Invalid run id')
    # Compatibility order matters: the old weekly runner owns ai-backup.lock
    # before calling the old local runner's homecontrol-backup.lock.
    locks=[]
    coordinated=False
    power=AiPowerCoordinator(root)
    try:
        names=('ai-backup.lock','homecontrol-backup.lock') if mode=='weekly' else ('homecontrol-backup.lock',)
        for name in names:
            handle=(root/name).open('a')
            locks.append(handle)
            try: fcntl.flock(handle,fcntl.LOCK_EX|(0 if wait else fcntl.LOCK_NB))
            except BlockingIOError: return 75
        settings_path=root/'backup_settings.json'
        stored=read_json(settings_path)
        if settings_path.exists() and stored is None: raise ValueError('Invalid backup settings')
        settings={**BackupService.DEFAULT_SETTINGS,**(stored or {})}
        if not backup_mode_allowed(mode, settings):
            job=read_json(root/'runs'/(run_id+'.json')) or dict(version=1,run_id=run_id,mode=mode,source=source,requested_at=now())
            job.update(state='failed',finished_at=now(),returncode=78,error=RESTRICTION_MESSAGE,
                       code='deployment_restricted',required_targets=[],targets={},scope='disabled')
            atomic_json(root/'runs'/(run_id+'.json'),job)
            atomic_json(root/'backup-state.json',job)
            return 78
        settings=effective_backup_settings(settings)
        validate_router(settings)
        if is_router(settings):
            settings['restic_repository']=router_repository(settings)
        required=required_targets(mode,settings)
        job=read_json(root/'runs'/(run_id+'.json')) or dict(version=1,run_id=run_id,mode=mode,source=source,requested_at=now())
        if job.get('state') in ('completed','failed'): return 0 if job['state']=='completed' else 1
        if not ai_disabled() and not is_router(settings):
            power.begin_backup(run_id)
            coordinated=True
        job.update(state='running',started_at=now(),pid=os.getpid(),required_targets=required,targets={})
        if ai_disabled():
            status=public_status()
            job.update(scope='router' if is_router(settings) and status['router_backup_enabled'] else 'local_only',
                       remote_backup_disabled=not status['remote_backup_enabled'],restriction_reason=status['message'])
        atomic_json(root/'runs'/(run_id+'.json'),job)
        atomic_json(root/'backup-state.json',job)
        # The original AI guard format is retained; no shutdown policy changes.
        if mode=='weekly' and not is_router(settings):
            atomic_json(root/'ai-backup-state.json',dict(state='running',updated_at=now(),pid=os.getpid(),run_id=run_id,detail=mode+' backup job'))
        with tempfile.TemporaryDirectory(prefix='hc-f6-') as work:
            snapshot=Path(work)/'settings.json';atomic_json(snapshot,settings,0o600)
            env={**os.environ,'BACKUP_ROOT':str(root),'HC_BACKUP_RUN_ID':run_id,
                 'HC_BACKUP_MODE':mode,'HC_BACKUP_WORK_DIR':work,'HC_BACKUP_SETTINGS_FILE':str(snapshot)}
            env['HC_BACKUP_LOCK_FD']=str(locks[-1].fileno())
            if message: env['GITEA_COMMIT_MESSAGE']=message
            log=os.fdopen(os.open(root/'backup.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600),'a')
            child=None;stopped=False
            def stop(signum,frame):
                nonlocal stopped
                stopped=True
                if child is not None:
                    try: os.killpg(child.pid,signal.SIGTERM)
                    except ProcessLookupError: pass
            previous={s:signal.signal(s,stop) for s in (signal.SIGINT,signal.SIGTERM)}
            try:
                child=subprocess.Popen(['bash',str(CODE/WORKERS[mode])],env=env,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                    pass_fds=tuple(h.fileno() for h in locks))
                try: rc=child.wait(timeout=int(env.get('HC_BACKUP_TIMEOUT_SECONDS','10800')))
                except subprocess.TimeoutExpired:
                    stop(signal.SIGTERM,None)
                    try: child.wait(timeout=10)
                    except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL);child.wait()
                    rc=124
                if stopped: rc=rc or 143
            finally:
                for s,handler in previous.items(): signal.signal(s,handler)
                log.close()
        job=read_json(root/'runs'/(run_id+'.json')) or job
        missing=[t for t in required if job.get('targets',{}).get(t,{}).get('state')!='succeeded']
        for name in missing:
            if job.get('targets',{}).get(name,{}).get('state') in (None,'running','skipped'):
                target(root,run_id,name,'failed','Required target did not finish')
        job=read_json(root/'runs'/(run_id+'.json')) or job
        success=rc==0 and not missing
        job.update(state='completed' if success else 'failed',finished_at=now(),returncode=rc,
                   error='' if success else 'Backup failed; inspect target results',missing_required_targets=missing)
        atomic_json(root/'runs'/(run_id+'.json'),job);atomic_json(root/'backup-state.json',job)
        if mode=='weekly' and not is_router(settings):
            atomic_json(root/'ai-backup-state.json',dict(state='idle' if success else 'failed',updated_at=now(),pid=os.getpid(),run_id=run_id,detail=job['state']))
        return 0 if success else 1
    finally:
        try:
            if coordinated: power.finish_backup(run_id)
        finally:
            for handle in reversed(locks): handle.close()


def execute(root, mode, *, source='timer', run_id=None, wait=False, message=''):
    run_id=run_id or uuid.uuid4().hex
    if not RUN_ID.fullmatch(run_id): raise ValueError('Invalid run id')
    try:
        return _execute(root,mode,source=source,run_id=run_id,wait=wait,message=message)
    except Exception:
        job=read_json(Path(root)/'runs'/(run_id+'.json'))
        if job:
            job.update(state='failed',finished_at=now(),error='Host runner failed before completion')
            try:
                atomic_json(Path(root)/'runs'/(run_id+'.json'),job)
                atomic_json(Path(root)/'backup-state.json',job)
            except OSError: pass  # Disk-full cannot be converted into success.
        print('Backup runner failed; inspect the private log and target state.',file=sys.stderr)
        return 1


def drain(root):
    root=Path(root);status=0
    for path in sorted((root/'requests').glob('*.json')):
        request=read_json(path,8192)
        if (not request or not RUN_ID.fullmatch(path.stem) or request.get('run_id')!=path.stem
            or request.get('version')!=1 or request.get('mode') not in ('local','weekly','git')
            or not isinstance(request.get('message',''),str) or len(request.get('message',''))>256
            or set(request)-{'version','run_id','mode','source','state','requested_at','message'}):
            # Invalid requests are quarantined, never executed as host commands.
            (root/'rejected').mkdir(exist_ok=True)
            path.rename(root/'rejected'/path.name)
            if RUN_ID.fullmatch(path.stem):
                job=read_json(root/'runs'/path.name)
                if job:
                    job.update(state='failed',error='Rejected invalid backup request',finished_at=now())
                    atomic_json(root/'runs'/path.name,job)
            status=1;continue
        try:
            if execute(root,request['mode'],source='web',run_id=request['run_id'],wait=True,message=request.get('message','')):
                status=1
        finally: path.unlink(missing_ok=True)
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(os.environ.get('BACKUP_ROOT','/srv/docker/homecontrol/backups')))
    commands=parser.add_mutually_exclusive_group(required=True)
    commands.add_argument('--mode',choices=MODES)
    commands.add_argument('--drain',action='store_true')
    commands.add_argument('--verify-existing',metavar='ARCHIVE')
    args=parser.parse_args()
    if args.drain: return drain(args.root)
    if args.verify_existing:
        from backup_protocol import verify_archive
        name=args.verify_existing
        if Path(name).name!=name or not name.endswith('.tar.gz'): parser.error('Archive basename required')
        path=args.root/name
        with (args.root/'homecontrol-backup.lock').open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            checked=verify_archive(path)
            receipt=dict(version=1,completed=True,name=name,mode='verified_existing',run_id=uuid.uuid4().hex,
                         timestamp=now(),mtime_ns=path.stat().st_mtime_ns,**checked)
            atomic_json(args.root/(name+'.complete.json'),receipt)
        return 0
    return execute(args.root,args.mode)


if __name__=='__main__':
    raise SystemExit(main())
