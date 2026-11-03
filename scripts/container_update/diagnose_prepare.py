#!/usr/bin/env python3
"""Read-only diagnosis of the r23 private-stage failure, with secrets withheld."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

BASE=Path('/srv/docker/homecontrol')
ORIGINAL=BASE/'backups/releases/hc-containers-20261103-r23'
CONTINUATION=BASE/'backups/releases/hc-containers-20261103-r23-continuation-1'


def metadata(path):
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink in private stage')
    if not path.exists():return {'exists':False}
    info=path.stat()
    return {'exists':True,'uid':info.st_uid,'gid':info.st_gid,'mode':oct(info.st_mode&0o777)}


def main():
    if os.geteuid()!=0:raise PermissionError('Local sudo is required for this read-only diagnosis')
    helper_path=Path(__file__).with_name('diagnose_start.py')
    spec=importlib.util.spec_from_file_location('r23_prepare_redaction',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    private=CONTINUATION/'private';state=ORIGINAL/'private'
    report={'read_only':True,'deployment_performed':False,'remote_commands':0,
        'active_release':json.loads((BASE/'infra/access-release.json').read_text()).get('release')}
    for key,path in (('error',private/'error.json'),('progress',state/'progress.json'),
                     ('original_evidence_preserved',private/'original-evidence-preserved.json')):
        if path.exists():
            raw,_=helper.private_bytes(path,16384);row=json.loads(raw)
            report[key]={k:v for k,v in row.items() if k in ('error_type','phase','ok','files')}
    raw,truncated=helper.private_bytes(private/'execution-private.log',2*1024**2)
    report['private_log']=dict(helper.summarize(raw.decode(errors='replace')),tail_only=truncated)
    proof_path=state/'pre-proof.json'
    if proof_path.exists():
        raw,_=helper.private_bytes(proof_path,16384);proof=json.loads(raw)
        report['pre_backup_restore']={k:proof[k] for k in ('ok','restore','database') if k in proof}
        for key,length in (('run_id',32),('snapshot_id',64),('archive_sha256',64)):
            value=proof.get(key)
            if isinstance(value,str) and re.fullmatch('[0-9a-f]{'+str(length)+'}',value):report['pre_backup_restore'][key]=value
    report['transition_exists']=(state/'transition').exists()
    report['new_runtime_exists']=(BASE/'scripts/access_runtime/hc-containers-20261103-r23').exists()
    report['new_private_exists']=(BASE/'infra/ssh/hc-containers-20261103-r23').exists()
    broker=state/'runtime/mqtt/broker'
    report['broker_stage_directory']=metadata(broker)
    report['broker_stage_configuration']=metadata(broker/'mosquitto.conf')
    if (broker/'mosquitto.conf').is_file():
        names=[]
        for line in (broker/'mosquitto.conf').read_text().splitlines():
            text=line.strip()
            if text and not text.startswith('#'):
                name=text.split()[0]
                if name in ('listener','bind_address','user','pid_file','persistence','persistence_location',
                            'log_dest','password_file','acl_file','per_listener_settings','max_packet_size',
                            'include_dir','plugin','allow_anonymous'):names.append(name)
        report['broker_config_directive_names']=sorted(set(names))
    for label,unit in (('original_worker_active','homecontrol-r23-container-update.service'),
                       ('continuation_worker_active','homecontrol-r23-inventory-continuation.service')):
        value=subprocess.run(['systemctl','show',unit,'--property=ActiveState,MainPID','--no-pager'],
            capture_output=True,text=True,timeout=10)
        props=dict(line.split('=',1) for line in value.stdout.splitlines() if '=' in line)
        report[label]=props.get('ActiveState') in ('active','activating','deactivating') or props.get('MainPID','0')!='0'
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
