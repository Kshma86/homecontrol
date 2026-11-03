"""Rollback only stopped MQTT/Zigbee data; keep exact ownership and mode."""
import json
import os
from pathlib import Path
import shutil
import stat

BASE=Path('/srv/docker/homecontrol')
ROOTS={'mqtt':BASE/'infra/mqtt/data','zigbee':BASE/'infra/zigbee2mqtt/data'}
SKIP={'zigbee':frozenset(('log','device_icons')),'mqtt':frozenset()}


def entries(root,skip):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('Expected real data directory')
    result=[]
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if relative.parts[0] in skip:continue
        if path.is_symlink() or not (path.is_dir() or path.is_file()):raise ValueError('Unexpected mutable data entry')
        info=path.stat()
        if path.is_file() and info.st_nlink!=1:raise ValueError('Hardlinked mutable data entry')
        result.append((path,relative,info))
    return result


def capture(destination):
    destination=Path(destination);destination.mkdir(mode=0o700,exist_ok=False)
    report={}
    for name,root in ROOTS.items():
        target=destination/name;target.mkdir(mode=0o700)
        rows=[]
        for path,relative,info in entries(root,SKIP[name]):
            out=target/relative
            if path.is_dir():out.mkdir(parents=True,exist_ok=True)
            else:
                out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,out)
            rows.append({'path':str(relative),'directory':path.is_dir(),'uid':info.st_uid,'gid':info.st_gid,
                         'mode':stat.S_IMODE(info.st_mode)})
        report[name]=rows
    (destination/'metadata.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'captured':True,'roots':list(report),'entries':sum(len(r) for r in report.values())}


def restore(destination):
    destination=Path(destination);report=json.loads((destination/'metadata.json').read_text())
    if set(report)!=set(ROOTS):raise ValueError('Snapshot root mismatch')
    # Validate every current entry and every saved path before removing anything.
    current={name:entries(root,SKIP[name]) for name,root in ROOTS.items()}
    for name,rows in report.items():
        for row in rows:
            rel=Path(row['path'])
            if rel.is_absolute() or '..' in rel.parts or rel.parts[0] in SKIP[name]:raise ValueError('Invalid saved data path')
            path=destination/name/rel
            if path.is_symlink() or not (path.is_dir() if row['directory'] else path.is_file()):raise ValueError('Missing saved data')
    for name,root in ROOTS.items():
        for path,_,_ in reversed(current[name]):
            if path.is_dir():path.rmdir()
            else:path.unlink()
        for row in report[name]:
            rel=Path(row['path']);out=root/rel
            if row['directory']:out.mkdir(parents=True,exist_ok=True)
            else:
                out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(destination/name/rel,out)
            os.chown(out,row['uid'],row['gid']);out.chmod(row['mode'])
    return {'restored':True,'roots':list(report)}
