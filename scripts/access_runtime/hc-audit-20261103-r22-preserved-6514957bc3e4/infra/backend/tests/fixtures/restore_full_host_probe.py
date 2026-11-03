"""Run only as root inside a networkless disposable container with canonical tmpfs."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

BASE=Path('/srv/docker/homecontrol')
if os.environ.get('HC_RESTORE_ISOLATED')!='1' or os.geteuid()!=0 or Path('/var/run/docker.sock').exists():
    raise SystemExit('Disposable isolated container required')
mounts=[line.split() for line in Path('/proc/mounts').read_text().splitlines()]
if not any(row[1]==str(BASE) and row[2]=='tmpfs' for row in mounts):
    raise SystemExit('Canonical target must be a disposable tmpfs')
FIXTURE=Path('/fixture');WORK=Path('/tmp/full-host');WORK.mkdir()
BIN=WORK/'bin';BIN.mkdir();TRACE=WORK/'trace.jsonl';STATE=WORK/'manager.json'
FAKE=r'''#!/usr/bin/env python3
import json,os,pathlib,shutil,sys
name=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:]
trace=pathlib.Path(os.environ['HC_PROBE_TRACE'])
with trace.open('a') as s:s.write(json.dumps({'command':name,'args':a})+'\n')
fixture=pathlib.Path('/fixture')
if name=='git':
 if a[0]=='clone':shutil.copytree(fixture/'repo',a[-1],dirs_exist_ok=True);(pathlib.Path(a[-1])/'.git').mkdir(exist_ok=True)
elif name=='age':sys.stdout.buffer.write((fixture/'secrets.tar.gz').read_bytes())
elif name=='restic':
 if 'snapshots' in a:print(json.dumps([{'id':'a'*64,'tags':['homecontrol'],'time':'2026-01-01'},{'id':'b'*64,'tags':['other'],'time':'2026-02-01'}]))
 elif 'restore' in a:
  assert a[a.index('restore')+1]=='a'*64
  shutil.copytree(fixture/'snapshot',a[a.index('--target')+1],dirs_exist_ok=True)
elif name=='rsync':
 source,target=a[-2:]
 shutil.copytree(source,target,dirs_exist_ok=True,symlinks=True,ignore=shutil.ignore_patterns('.git'))
elif name=='docker':
 if a[0]=='cp':
  data=pathlib.Path(a[1]).read_bytes()
  with trace.open('a') as s:s.write(json.dumps({'selected_dump':data.decode()})+'\n')
 if a[0]=='exec' and '-i' in a:sys.stdin.read()
elif name=='systemctl':
 path=pathlib.Path(os.environ['HC_PROBE_MANAGER']);state=json.loads(path.read_text()) if path.exists() else {}
 command=a[0]
 if command=='is-active':sys.exit(0 if state.get(a[-1],{}).get('active') else 3)
 if command=='is-enabled':
  enabled=state.get(a[-1],{}).get('enabled',False);print('enabled' if enabled else 'disabled');sys.exit(0 if enabled else 1)
 if command in ('enable','disable','stop'):
  for unit in a[1:]:
   if unit.startswith('--'):continue
   old=state.setdefault(unit,{'enabled':False,'active':False})
   if command!='stop':old['enabled']=command=='enable'
   old['active']=command=='enable'
  path.write_text(json.dumps(state))
 if command=='show':print('NextElapseUSecRealtime=Tue 2026-10-27 02:15:00 CET\nNextElapseUSecMonotonic=0')
else:raise SystemExit('Unexpected external command')
'''
fake=BIN/'fake';fake.write_text(FAKE);fake.chmod(0o755)
for name in ('git','age','restic','rsync','docker','systemctl','ssh'):(BIN/name).symlink_to(fake)
env={**os.environ,'PATH':str(BIN)+':'+os.environ['PATH'],'HC_PROBE_TRACE':str(TRACE),'HC_PROBE_MANAGER':str(STATE)}
sys.path.insert(0,'/source/infra/backend')
from backup_protocol import seal


def archive(label,db=True,corrupt=False):
    directory=WORK/('source-'+label);directory.mkdir()
    (directory/'scripts').mkdir();(directory/'scripts/probe.sh').write_text('#!/bin/sh\nexit 0\n')
    if db:(directory/'postgres').mkdir();(directory/'postgres/db.dump').write_text(label)
    seal(directory,'local',{'postgres':db})
    if corrupt:(directory/'scripts/probe.sh').write_text('corrupt')
    snapshot=FIXTURE/'snapshot/srv/docker/homecontrol/backups';snapshot.mkdir(parents=True,exist_ok=True)
    for old in snapshot.iterdir():old.unlink()
    with tarfile.open(snapshot/('homecontrol_'+label+'.tar.gz'),'w:gz') as tar:tar.add(directory,arcname=label)


def run(label,success=True):
    TRACE.unlink(missing_ok=True)
    args=['bash','/source/scripts/bootstrap_restore_v0_1.sh','--age-key',str(FIXTURE/'key'),
          '--work-dir',str(WORK/'reused-work'),'--apply','--apply-restic-files','--restore-db','--confirm-db-replace','--start']
    result=subprocess.run(args,env=env,capture_output=True,text=True)
    (WORK/(label+'.log')).write_text(result.stdout+result.stderr)
    rows=[json.loads(line) for line in TRACE.read_text().splitlines()] if TRACE.exists() else []
    if bool(result.returncode==0)!=success:raise AssertionError(label+': '+(result.stdout+result.stderr)[-2500:])
    return rows


archive('NEW');first=run('first')
assert [row['selected_dump'] for row in first if 'selected_dump' in row]==['NEW']
installed=json.loads((BASE/'backups/f6-installed.json').read_text())
assert len(installed['units'])==14 and installed['next_triggers']
assert installed['scope']=='system'
unit_bytes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/etc/systemd/system').glob('homecontrol-*') if p.is_file()}
archive('OLD');second=run('second')
assert [row['selected_dump'] for row in second if 'selected_dump' in row]==['OLD']
assert unit_bytes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/etc/systemd/system').glob('homecontrol-*') if p.is_file()}
sentinel=BASE/'sentinel';sentinel.write_text('UNCHANGED')
archive('NO_DB',db=False);missing=run('missing-db',success=False)
assert not any(row.get('command')=='docker' for row in missing)
archive('BAD_SHA',corrupt=True);bad=run('bad-sha',success=False)
assert not any(row.get('command')=='docker' for row in bad)
assert sentinel.read_text()=='UNCHANGED'
assert not any(row.get('command')=='runuser' for row in first+second)
summary=dict(full_bootstrap_runs=2,selected_dumps=['NEW','OLD'],unit_count=14,idempotent_units=True,
             missing_db_refused_before_docker=True,checksum_refused_before_docker=True,canonical_sentinel_unchanged=True,
             real_systemd_manager=False,real_docker_daemon=False,external_network=False)
Path('/evidence/full-host-probe.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
