"""Fixed HC-41/44 release locations and safe filesystem operations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

BASE = Path('/srv/docker/homecontrol')
NAME = 'hc-router-backup-20261101-r14'
RUNTIME = BASE/'scripts/access_runtime'/NAME
PRIVATE = BASE/'infra/ssh'/NAME
SERVICES = ('backend', 'hc_ingest', 'homecontrol-tuya-poller', 'homecontrol-xiaomi-x10',
            'homecontrol-gree-climate', 'homecontrol-ha-growatt-poller', 'mqtt', 'zigbee2mqtt',
            'postgres', 'pgbouncer', 'frontend', 'proxy', 'ai-server')
QUIESCE = ('homecontrol-backup.timer','homecontrol-ai-weekly-backup.timer',
           'homecontrol-restic-check.timer','homecontrol-log-maintenance.timer',
           'homecontrol-backup-apply.path','homecontrol-full-ai-backup-request.path',
           'homecontrol-post-boot-health.timer')


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def write_json(path, value, mode=0o600):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    with temporary.open('x') as stream:
        os.fchmod(stream.fileno(),mode);json.dump(value,stream,indent=2);stream.write('\n')
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def no_symlinks(path):
    path=Path(path).absolute()
    for item in (path,*path.parents):
        if item.is_symlink():raise ValueError('Symlink in protected path: '+str(item))


def cancel_intent(state, reason):
    if not isinstance(state,dict) or state.get('version')!=1:raise ValueError('Invalid AI coordination state')
    state=copy.deepcopy(state)
    if (state.get('backup') or {}).get('active'):raise ValueError('Active backup state must be reconciled first')
    state.update(generation=uuid.uuid4().hex,intent=None,last_cancel={'reason':reason})
    return state


def snapshot(paths, destination):
    destination=Path(destination);destination.mkdir(mode=0o700,parents=True,exist_ok=False)
    rows=[]
    for number,path in enumerate(map(Path,paths)):
        if path.is_symlink():
            rows.append(dict(path=str(path),type='symlink',target=os.readlink(path)));continue
        if not path.exists():rows.append(dict(path=str(path),type='missing'));continue
        info=path.stat()
        if not stat.S_ISREG(info.st_mode):raise ValueError('Snapshot requires regular file: '+str(path))
        name=str(number);shutil.copyfile(path,destination/name)
        rows.append(dict(path=str(path),type='file',copy=name,mode=stat.S_IMODE(info.st_mode),uid=info.st_uid,gid=info.st_gid))
    write_json(destination/'files.json',rows)
    return rows


def restore_snapshot(directory):
    directory=Path(directory)
    for row in json.loads((directory/'files.json').read_text()):
        path=Path(row['path']);no_symlinks(path.parent);path.parent.mkdir(parents=True,exist_ok=True)
        if path.is_symlink() or path.exists():path.unlink()
        if row['type']=='symlink':path.symlink_to(row['target'])
        elif row['type']=='file':
            shutil.copyfile(directory/row['copy'],path);path.chmod(row['mode']);os.chown(path,row['uid'],row['gid'])


def units(source, runtime=RUNTIME):
    source=Path(source);result={}
    for path in (source/'scripts/systemd/hostops').rglob('*'):
        if path.is_file():result[path.relative_to(source/'scripts/systemd/hostops').as_posix()]=path.read_text().replace(str(BASE)+'/scripts/hostops',str(runtime)+'/scripts/hostops')
    result['homecontrol-post-boot-health.service.d/hc-access.conf']='[Service]\nExecStart=\nExecStart=/bin/bash '+str(runtime)+'/scripts/mqtt_access/post_boot_health.sh\n'
    result['homecontrol-post-boot-health.timer']=(source/'scripts/systemd/homecontrol-post-boot-health.timer').read_text()
    result['homecontrol-backup-apply.service.d/hc-access.conf']='[Service]\nExecStart=\nExecStart=/usr/bin/python3 '+str(runtime)+'/scripts/access_release/restore_host.py --apply\n'
    # No ExecStop: stopping/restarting this unit must not open anonymous MQTT.
    result['homecontrol-mqtt-access.service']='''[Unit]
Description=HomeControl MQTT legacy source restriction
After=docker.service
Requires=docker.service
PartOf=docker.service
Before=homecontrol-hostops.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 '''+str(runtime)+'''/scripts/access_release/network.py --policy '''+str(PRIVATE)+'''/network-policy.json --apply
[Install]
WantedBy=multi-user.target
'''
    result['homecontrol-hostops.service.d/hc-access.conf']='[Unit]\nRequires=homecontrol-mqtt-access.service\nAfter=homecontrol-mqtt-access.service\n'
    # Install the restriction before containers can auto-start after a reboot.
    # Retained on rollback along with the guard; it reads the rollback policy.
    result['docker.service.d/hc-access.conf']='[Service]\nExecStartPre=/usr/bin/python3 '+str(runtime)+'/scripts/access_release/network.py --policy '+str(PRIVATE)+'/network-policy.json --apply\n'
    return result
