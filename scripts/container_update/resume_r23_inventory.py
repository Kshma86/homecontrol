#!/usr/bin/env python3
"""Continue only the proven pre-transition MQTT inventory-size failure."""
from contextlib import redirect_stdout
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
PACKAGE=BASE/'backups/releases/hc-containers-20261103-r23-continuation-1'
SOURCE=PACKAGE/'source'
STATE=PACKAGE/'private'
ORIGINAL_MANIFEST='f5593892ad51d1aead57eb7d5bb2f38145ba04ae6e3ad9c7c5c94d9941eb90fa'
ORIGINAL_ACCEPTANCE='fb5044c009ad010d5bed273447f9cc1063e4c903ccf32f7bf4204cb162b8336d'
ORIGINAL_LAUNCHER='4eddcdbabe4d26f60dccbc76467a2a33fe4da11d2635dda33ae975d0875fb26f'
ORIGINAL_PRIVATE=ORIGINAL/'private'
PRESERVED=('activation-attempt.json','activation-error.json','activation-private.log')
ALLOWED_ORIGINAL_ENTRIES=set(PRESERVED)|{'access-images.tar.gz','intermediate-six-image-access-images.tar.gz','operator.lock'}
UNIT='homecontrol-r23-inventory-continuation'


def read(path):return json.loads(Path(path).read_text())


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def no_symlinks(path):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink in continuation path')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def verify_package():
    acceptance=read(PACKAGE/'acceptance.json')
    if acceptance.get('ok') is not True:raise ValueError('Continuation is not accepted')
    for name,expected in acceptance['source_sha256'].items():
        path=SOURCE/name;no_symlinks(path)
        if sha(path)!=expected:raise ValueError('Continuation source changed')
    for name,expected in acceptance['evidence_sha256'].items():
        path=PACKAGE/'evidence'/name;no_symlinks(path)
        if sha(path)!=expected:raise ValueError('Continuation evidence changed')
    for path,expected in ((ORIGINAL/'release.json',ORIGINAL_MANIFEST),
                          (ORIGINAL/'evidence/acceptance.json',ORIGINAL_ACCEPTANCE),
                          (ORIGINAL/'source/scripts/container_update/activate.py',ORIGINAL_LAUNCHER)):
        no_symlinks(path)
        if sha(path)!=expected:raise ValueError('Original release seal changed')
    manifest=read(ORIGINAL/'release.json')
    for name,expected in manifest['source_sha256'].items():
        path=ORIGINAL/'source'/name;no_symlinks(path)
        if sha(path)!=expected:raise ValueError('Frozen r23 source changed')
    return manifest


def validate_diagnosis(report):
    if report.get('active_release')!=OLD or report.get('worker_active') is not False:
        raise ValueError('Original worker or active release differs')
    if report.get('new_runtime_exists') is not False or report.get('new_private_exists') is not False:
        raise ValueError('Runtime already created; continuation refused')
    if report.get('recorded_error_type')!='RuntimeError' or report.get('recorded_phase')!='starting':
        raise ValueError('Failure is not the proven early inventory failure')
    entries=report.get('private_entries_present',{})
    expected={'activation-attempt.json':True,'activation-error.json':True,'activation-private.log':True,
              'progress.json':False,'paused-units.json':False,'pre-proof.json':False,'post-proof.json':False,
              'runtime':False,'transition':False}
    if entries!=expected:raise ValueError('Original execution advanced or evidence is missing')
    log=report.get('private_log',{})
    if (log.get('tail_only') is not False or log.get('last_command_kind')!='zigbee_bridge_devices_read'
            or set(log.get('conditions',[]))!={'mqtt_probe_no_message','private_command_failed'}
            or set(log.get('error_types',[]))!={'RuntimeError','TimeoutError'}):
        raise ValueError('Original private log does not prove the exact inventory failure')
    frames=log.get('traceback_frames',[])
    if not any(f.get('file')=='activate.py' and f.get('function')=='bridge' and f.get('line')==68 for f in frames):
        raise ValueError('Failure did not originate in the frozen bridge probe')


def guard():
    diagnostic=load('r23_inventory_start_diagnosis',SOURCE/'diagnose_start.py')
    output=io.StringIO()
    with redirect_stdout(output):diagnostic.main()
    report=json.loads(output.getvalue());validate_diagnosis(report)
    no_symlinks(ORIGINAL_PRIVATE)
    if set(p.name for p in ORIGINAL_PRIVATE.iterdir())-ALLOWED_ORIGINAL_ENTRIES:
        raise ValueError('Additional private execution state requires reconciliation')
    attempt=read(ORIGINAL_PRIVATE/'activation-attempt.json')
    if attempt!={'release':NAME,'one_shot':True}:raise ValueError('Original attempt receipt changed')
    receipt={}
    for name in PRESERVED:
        path=ORIGINAL_PRIVATE/name;no_symlinks(path);info=path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o077:
            raise ValueError('Untrusted original private receipt')
        receipt[name]=sha(path)
    return report,receipt


def wire(executor,helper,inventory,core):
    # Keep the reviewed execution, cutover, backup, restore and rollback code.
    executor.bridge=inventory.bridge
    core.call=lambda args,**kwargs:executor.adapter_call(helper,args,**kwargs)
    previous_phase=core.phase
    def phase(name):
        helper.PHASE=name;print('Konténerfrissítés: '+name,flush=True);previous_phase(name)
    core.phase=phase


def worker():
    verify_package()
    no_symlinks(STATE);no_symlinks(STATE/'attempt.json')
    info=STATE.stat()
    if info.st_uid!=0 or info.st_mode&0o077 or read(STATE/'attempt.json')!={'release':NAME,'one_shot':True}:
        raise ValueError('Supervised continuation receipt required')
    executor=load('r23_frozen_inventory_executor',ORIGINAL/'source/scripts/container_update/activate.py')
    signal.signal(signal.SIGTERM,executor.interrupted);signal.signal(signal.SIGINT,executor.interrupted)
    if sha(executor.HOST_EXECUTOR)!=executor.HOST_EXECUTOR_SHA:raise ValueError('Backup helper changed')
    helper=executor.load('r23_continuation_backup_helper',executor.HOST_EXECUTOR)
    helper.STATE=ORIGINAL_PRIVATE;helper.RUNTIME=BASE/'scripts/access_runtime'/OLD
    helper.say=lambda value:print(value.replace('Hostkarbantartás:','Konténerfrissítés:',1),flush=True)
    helper.LOG=(STATE/'execution-private.log').open('x')
    preserved=None
    try:
        # Original and continuation workers share the same operator lock.
        lock=ORIGINAL_PRIVATE/'operator.lock';no_symlinks(lock)
        with lock.open('a') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            report,preserved=guard()
            helper.write(STATE/'original-diagnosis.json',report)
            helper.write(STATE/'preserved-original-sha256.json',preserved)
            inventory=load('r23_continuation_bounded_inventory',SOURCE/'zigbee_inventory.py')
            core=executor.load('r23_continuation_core',executor.SOURCE/'scripts/f10_release/deploy.py')
            wire(executor,helper,inventory,core)
            print('Az r23 pontos Zigbee-lista méretkorláthibája és a változatlan r22 ellenőrzött. '
                  'Az eredeti indítási jelző megmarad; minden előmentési, restore- és átállítási kapu újrafut.',flush=True)
            executor.execute(core,helper)
            helper.write(STATE/'result.json',{'ok':True,'release':NAME,
                'state':'container_updates_backup_restore_verified','original_attempt_preserved':True})
    except BaseException as error:
        traceback.print_exc(file=helper.LOG);helper.LOG.flush()
        helper.write(STATE/'error.json',{'error_type':type(error).__name__,'phase':helper.PHASE})
        print('Az r23 folytatás megállt: '+type(error).__name__+'. Privát napló megőrizve; ne ismételd vakon.',flush=True)
        raise SystemExit(1)
    finally:
        if preserved is not None:
            unchanged=all(sha(ORIGINAL_PRIVATE/name)==expected for name,expected in preserved.items())
            helper.write(STATE/'original-evidence-preserved.json',{'ok':unchanged,'files':len(preserved)})
        helper.LOG.close()


def status():
    result={'release':NAME,'active_release':read(BASE/'infra/access-release.json').get('release'),
            'continuation_started':(STATE/'attempt.json').exists()}
    for name in ('error.json','result.json','original-evidence-preserved.json'):
        path=STATE/name
        if path.is_file():no_symlinks(path);result[name]=read(path)
    for name in ('progress.json','transition/result.json'):
        path=ORIGINAL_PRIVATE/name
        if path.is_file():no_symlinks(path);result[name]=read(path)
    log=STATE/'execution-private.log'
    if log.exists():
        diagnostic=load('r23_continuation_status_diagnosis',SOURCE/'diagnose_start.py')
        raw,truncated=diagnostic.private_bytes(log,2*1024**2)
        result['private_log']=dict(diagnostic.summarize(raw.decode(errors='replace')),tail_only=truncated)
    print(json.dumps(result,indent=2))


def main():
    os.umask(0o077)
    if os.geteuid()!=0:raise PermissionError('Local sudo is required')
    if sys.argv[1:]==['status']:status();return
    if sys.argv[1:]==['_worker']:worker();return
    if sys.argv[1:]:raise ValueError('Unsupported continuation arguments')
    verify_package();guard()
    no_symlinks(STATE);STATE.mkdir(mode=0o700,exist_ok=True);os.chown(STATE,0,0);STATE.chmod(0o700)
    with (STATE/'attempt.json').open('x') as stream:json.dump({'release':NAME,'one_shot':True},stream)
    command=['systemd-run','--quiet','--wait','--pipe','--collect','--unit='+UNIT,
        '--property=Type=exec','--property=KillMode=mixed','--property=RuntimeMaxSec=28800',
        '--property=TimeoutStopSec=900','--property=UMask=0077','/usr/bin/python3','-B',
        str(SOURCE/'resume_r23_inventory.py'),'_worker']
    raise SystemExit(subprocess.run(command).returncode)


if __name__=='__main__':main()
