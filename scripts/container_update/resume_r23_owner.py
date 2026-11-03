#!/usr/bin/env python3
"""Resume the proven pre-transition broker-config ownership failure."""
from contextlib import ExitStack,redirect_stdout
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import traceback

sys.dont_write_bytecode=True
BASE=Path('/srv/docker/homecontrol')
NAME='hc-containers-20261103-r23'
OLD='hc-audit-20261103-r22'
ORIGINAL=BASE/'backups/releases'/NAME
PREVIOUS=BASE/'backups/releases/hc-containers-20261103-r23-continuation-1'
PACKAGE=BASE/'backups/releases/hc-containers-20261103-r23-continuation-2'
SOURCE=PACKAGE/'source'
STATE=PACKAGE/'private'
PRIV=ORIGINAL/'private'
HISTORY=PRIV/'preserved-before-owner-continuation'
PREVIOUS_SEAL='8d3bd54e8e98e97374f6bca35c0d26890cddd85a8d6d100bca5ae6ace1797a59'
KEEP={'activation-attempt.json','activation-error.json','activation-private.log',
      'operator.lock','access-images.tar.gz','intermediate-six-image-access-images.tar.gz'}
UNIT='homecontrol-r23-owner-continuation'


def read(path):return json.loads(Path(path).read_text())


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def safe(path):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink in continuation path')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def verify():
    acceptance=read(PACKAGE/'acceptance.json')
    if acceptance.get('ok') is not True:raise ValueError('Continuation acceptance incomplete')
    for folder,key in (('source','source_sha256'),('evidence','evidence_sha256')):
        for name,expected in acceptance[key].items():
            path=PACKAGE/folder/name;safe(path)
            if sha(path)!=expected:raise ValueError('Continuation seal changed')
    safe(PREVIOUS/'acceptance.json')
    if sha(PREVIOUS/'acceptance.json')!=PREVIOUS_SEAL:raise ValueError('Previous continuation seal changed')
    previous=load('r23_owner_previous_sealed_continuation',PREVIOUS/'source/resume_r23_inventory.py')
    previous.verify_package()
    return previous


def validate(report):
    if report.get('active_release')!=OLD:raise ValueError('Expected r22 baseline')
    if report.get('original_worker_active') is not False or report.get('continuation_worker_active') is not False:
        raise ValueError('An earlier worker is still active')
    if any(report.get(key) is not False for key in ('transition_exists','new_runtime_exists','new_private_exists')):
        raise ValueError('Existing cutover blocks owner continuation')
    if report.get('error')!={'error_type':'RuntimeError','phase':'prepare_new_private_runtime'}:
        raise ValueError('Different preceding error')
    if report.get('progress')!={'phase':'prepare_new_private_runtime'}:
        raise ValueError('Different preceding progress')
    if report.get('original_evidence_preserved')!={'ok':True,'files':3}:
        raise ValueError('Original evidence preservation is not verified')
    log=report.get('private_log',{})
    if (log.get('tail_only') is not False or set(log.get('conditions',[]))!={'mosquitto_config_unreadable','private_command_failed'}
            or set(log.get('error_types',[]))!={'RuntimeError'}):
        raise ValueError('Unproven broker ownership failure')
    if not any(f.get('file')=='activate.py' and f.get('function')=='private_mqtt_probe' and f.get('line')==115
               for f in log.get('traceback_frames',[])):
        raise ValueError('Broker failed at a different execution boundary')
    proof=report.get('pre_backup_restore',{})
    if any(proof.get(key)!=value for key,value in {'ok':True,'restore':'verified','database':'verified'}.items()):
        raise ValueError('No verified preceding backup and restore')
    for key,mode in (('broker_stage_directory','0o700'),('broker_stage_configuration','0o600')):
        if report.get(key)!={'exists':True,'uid':1883,'gid':1883,'mode':mode}:
            raise ValueError('Private broker stage ownership differs')


def guard(previous):
    diagnostic=load('r23_owner_exact_failure_diagnosis',SOURCE/'diagnose_prepare.py')
    output=io.StringIO()
    with redirect_stdout(output):diagnostic.main()
    report=json.loads(output.getvalue());validate(report)
    if HISTORY.exists():raise ValueError('Earlier owner continuation history exists')
    for name in ('transition','post-proof.json','real-mqtt-proof.json','secret-receipt.json','homecontrol-secrets-r13.tar.gz.age'):
        if (PRIV/name).exists():raise ValueError('Execution passed the proven broker preflight boundary')
    preserved=read(PREVIOUS/'private/preserved-original-sha256.json')
    if set(preserved)!=set(previous.PRESERVED):raise ValueError('Original receipt inventory differs')
    for name,expected in preserved.items():
        path=PRIV/name;safe(path)
        if sha(path)!=expected:raise ValueError('Original attempt evidence changed')
    proof=read(PRIV/'pre-proof.json')
    if any(proof.get(key)!=value for key,value in {'ok':True,'restore':'verified','database':'verified'}.items()):
        raise ValueError('Invalid preceding restore receipt')
    return report,preserved


def preserve(helper):
    """Atomically move only inactive private execution inputs; retain every byte."""
    safe(PRIV);safe(HISTORY)
    if HISTORY.exists():raise ValueError('Preserved execution destination already exists')
    paths=sorted(p for p in PRIV.iterdir() if p.name not in KEEP)
    rows=[]
    # Validate every entry before moving any. Live runtime/private paths are outside PRIV.
    for path in paths:
        safe(path);info=path.stat()
        if path.is_mount() or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError('Unexpected private execution entry')
        row={'name':path.name,'device':info.st_dev,'inode':info.st_ino,
             'directory':path.is_dir(),'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}
        if path.is_file():row['sha256']=sha(path)
        rows.append(row)
    journal={'planned':rows,'moved':[],'completed':False}
    helper.write(STATE/'preservation.json',journal)
    HISTORY.mkdir(mode=0o700)
    for row in rows:
        source=PRIV/row['name'];target=HISTORY/row['name']
        current=source.stat()
        if (current.st_dev,current.st_ino)!=(row['device'],row['inode']):raise ValueError('Execution state changed before preservation')
        os.rename(source,target)
        after=target.stat()
        if (after.st_dev,after.st_ino)!=(row['device'],row['inode']):raise ValueError('Preserved execution inode differs')
        if not row['directory'] and sha(target)!=row['sha256']:raise ValueError('Preserved execution bytes differ')
        journal['moved'].append(row['name']);helper.write(STATE/'preservation.json',journal)
    journal['completed']=True;helper.write(STATE/'preservation.json',journal)


def wire(previous,executor,helper,inventory,owner,core):
    previous.wire(executor,helper,inventory,core)
    owner.install(executor)


def worker():
    previous=verify();safe(STATE);safe(STATE/'attempt.json')
    if STATE.stat().st_uid!=0 or STATE.stat().st_mode&0o077 or read(STATE/'attempt.json')!={'release':NAME,'one_shot':True}:
        raise ValueError('Supervised continuation receipt required')
    executor=load('r23_owner_frozen_executor',ORIGINAL/'source/scripts/container_update/activate.py')
    signal.signal(signal.SIGTERM,executor.interrupted);signal.signal(signal.SIGINT,executor.interrupted)
    if sha(executor.HOST_EXECUTOR)!=executor.HOST_EXECUTOR_SHA:raise ValueError('Frozen backup helper changed')
    helper=executor.load('r23_owner_backup_helper',executor.HOST_EXECUTOR)
    helper.STATE=PRIV;helper.RUNTIME=BASE/'scripts/access_runtime'/OLD
    helper.say=lambda text:print(text.replace('Hostkarbantartás:','Konténerfrissítés:',1),flush=True)
    helper.LOG=(STATE/'execution-private.log').open('x');preserved=None
    try:
        lock=PRIV/'operator.lock';safe(lock)
        with lock.open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            report,preserved=guard(previous);helper.write(STATE/'preceding-diagnosis.json',report)
            helper.write(STATE/'preserved-original-sha256.json',preserved)
            core=executor.load('r23_owner_core',executor.SOURCE/'scripts/f10_release/deploy.py')
            inventory=load('r23_owner_bounded_inventory',SOURCE/'zigbee_inventory.py')
            owner=load('r23_owner_broker_adapter',SOURCE/'mqtt_probe_owner.py')
            wire(previous,executor,helper,inventory,owner,core)
            manifest=core.verify();core.guard_runtime(manifest);helper.idle();helper.space_guard()
            with ExitStack() as stack:
                helper.common_locks(stack);preserve(helper)
            print('Az r23 pontos MQTT-próbajogosultsági hibája és az r22 állapot ellenőrzött. '
                  'A korábbi staging és nyugták megőrizve; a broker-próba a konfiguráció tulajdonosaként fut. '
                  'Minden teljes előmentési, restore- és átállítási kapu újrafut.',flush=True)
            executor.execute(core,helper)
            helper.write(STATE/'result.json',{'ok':True,'release':NAME,'state':'container_updates_backup_restore_verified'})
    except BaseException as error:
        traceback.print_exc(file=helper.LOG);helper.LOG.flush()
        helper.write(STATE/'error.json',{'error_type':type(error).__name__,'phase':helper.PHASE})
        print('Az r23 második folytatása megállt: '+type(error).__name__+'. Privát napló megőrizve; ne ismételd vakon.',flush=True)
        raise SystemExit(1)
    finally:
        if preserved is not None:
            helper.write(STATE/'original-evidence-preserved.json',{'ok':all(sha(PRIV/n)==h for n,h in preserved.items()),'files':len(preserved)})
        helper.LOG.close()


def status():
    result={'release':NAME,'active_release':read(BASE/'infra/access-release.json').get('release'),
            'started':(STATE/'attempt.json').exists()}
    for label,path in (('error',STATE/'error.json'),('result',STATE/'result.json'),
                       ('original_evidence_preserved',STATE/'original-evidence-preserved.json'),
                       ('progress',PRIV/'progress.json'),('transition',PRIV/'transition/result.json')):
        if path.is_file():safe(path);result[label]=read(path)
    if (STATE/'execution-private.log').exists():
        diagnostic=load('r23_owner_status_redaction',SOURCE/'diagnose_start.py')
        raw,truncated=diagnostic.private_bytes(STATE/'execution-private.log',2*1024**2)
        result['private_log']=dict(diagnostic.summarize(raw.decode(errors='replace')),tail_only=truncated)
    if (STATE/'preservation.json').exists():
        value=read(STATE/'preservation.json');result['preservation']={'completed':value['completed'],'entries_moved':len(value['moved'])}
    print(json.dumps(result,indent=2))


def main():
    os.umask(0o077)
    if os.geteuid()!=0:raise PermissionError('Local sudo is required')
    if sys.argv[1:]==['status']:status();return
    if sys.argv[1:]==['_worker']:worker();return
    if sys.argv[1:]:raise ValueError('Unsupported continuation arguments')
    previous=verify();guard(previous)
    safe(STATE);STATE.mkdir(mode=0o700,exist_ok=True);os.chown(STATE,0,0);STATE.chmod(0o700)
    with (STATE/'attempt.json').open('x') as stream:json.dump({'release':NAME,'one_shot':True},stream)
    command=['systemd-run','--quiet','--wait','--pipe','--collect','--unit='+UNIT,
        '--property=Type=exec','--property=KillMode=mixed','--property=RuntimeMaxSec=28800',
        '--property=TimeoutStopSec=900','--property=UMask=0077','/usr/bin/python3','-B',str(SOURCE/'resume_r23_owner.py'),'_worker']
    raise SystemExit(subprocess.run(command).returncode)


if __name__=='__main__':main()
