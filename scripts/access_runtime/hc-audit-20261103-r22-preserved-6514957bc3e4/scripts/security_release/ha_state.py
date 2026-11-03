"""Private HA copies and exception-safe replacement for upgrade/rollback."""
import hashlib,json,os
from pathlib import Path
import shutil,stat,uuid
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup_ha_sqlite import snapshot


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(name):
 path=Path(name)
 if path.is_absolute() or '..' in path.parts or not name or '\x00' in name:
  raise ValueError('Unsafe HA snapshot member')
 return path


def capture(source,target):
 source=Path(source);target=Path(target)
 if source.is_symlink() or not source.is_dir() or target.exists() or target.is_symlink():
  raise ValueError('Unexpected Home Assistant snapshot paths')
 target.mkdir(mode=0o700,parents=True)
 info=source.stat()
 directories={'.':{'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}}
 metadata={}
 for path in sorted(source.rglob('*')):
  relative=path.relative_to(source)
  if path.is_symlink():raise ValueError('HA snapshot cannot follow links')
  if path.name.startswith(('home-assistant.log','home-assistant_v2.db','.ha_run.lock')):continue
  info=path.stat();destination=target/relative
  if stat.S_ISDIR(info.st_mode):
   destination.mkdir(mode=0o700,parents=True,exist_ok=True)
   directories[str(relative)]={'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
  elif stat.S_ISREG(info.st_mode):
   destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
   shutil.copyfile(path,destination);destination.chmod(0o600)
   metadata[str(relative)]={'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),'sha256':digest(destination)}
  else:raise ValueError('Unexpected HA snapshot file type')
 sqlite=snapshot(source,target)
 if sqlite['present']:
  info=(source/'home-assistant_v2.db').stat()
  metadata['home-assistant_v2.db']={'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),'sha256':digest(target/'home-assistant_v2.db')}
 receipt={'completed':True,'files':metadata,'directories':directories,'sqlite':sqlite}
 (target/'.hc-snapshot.json').write_text(json.dumps(receipt,indent=2)+'\n');(target/'.hc-snapshot.json').chmod(0o600)
 return receipt


def replace(snapshot_directory,target_directory):
 """Keep the current directory recoverable if the second rename fails."""
 source=Path(snapshot_directory);target=Path(target_directory)
 receipt=json.loads((source/'.hc-snapshot.json').read_text())
 if not receipt['completed'] or source.is_symlink() or target.is_symlink():raise ValueError('Invalid HA rollback snapshot')
 for path in source.rglob('*'):
  if path.is_symlink() or not(path.is_dir() or path.is_file()):raise ValueError('Unexpected HA snapshot member')
 for name,row in receipt['files'].items():
  path=source/relative(name)
  if not re.fullmatch(r'[0-9a-f]{64}',row['sha256']):raise ValueError('Invalid HA snapshot digest')
  if path.is_symlink() or not path.is_file() or digest(path)!=row['sha256']:
   raise ValueError('HA snapshot content changed')
 temporary=target.with_name('.'+target.name+'.restore-'+uuid.uuid4().hex)
 quarantine=target.with_name('.'+target.name+'.before-'+uuid.uuid4().hex)
 if temporary.exists() or quarantine.exists():raise ValueError('Unexpected HA restore destination')
 shutil.copytree(source,temporary)
 (temporary/'.hc-snapshot.json').unlink()
 for name,row in receipt['files'].items():
  p=temporary/relative(name)
  if os.geteuid()==0:os.chown(p,row['uid'],row['gid'])
  p.chmod(row['mode'])
 for name,row in sorted(receipt['directories'].items(),key=lambda item:len(Path(item[0]).parts),reverse=True):
  p=temporary/relative(name)
  if os.geteuid()==0:os.chown(p,row['uid'],row['gid'])
  p.chmod(row['mode'])
 moved=False
 try:
  if target.exists():os.replace(target,quarantine);moved=True
  try:os.replace(temporary,target)
  except BaseException:
   if moved:os.replace(quarantine,target)
   raise
 finally:
  if temporary.exists():shutil.rmtree(temporary)
 return quarantine if moved else None
