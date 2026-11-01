#!/usr/bin/env python3
"""Apply explicit recovery corrections to a new lab Git commit; preserve upstream."""
import json
from pathlib import Path
import subprocess
import lab_vm

BASE = Path('/srv/docker/homecontrol')
FILES = (
    'infra/backend/backup_export.py', 'infra/backend/backup_export_manifest.py',
    'scripts/export_config_snapshot.py', 'scripts/backup_offsite_worker.sh',
    'scripts/backup_config_sync_worker.sh', 'scripts/access_release/restore_assets.py',
    'scripts/access_release/install.py',
    'infra/backend/tests/test_backup_restore_contract.py', 'infra/backend/tests/test_access_release.py',
)
lab_vm.ssh(['sudo', 'mkdir', '-p', '/lab/corrections'])
mapping = {}
for index, name in enumerate(FILES + ('scripts/router_release/bootstrap_restore_candidate.sh',)):
    target = '/lab/corrections/' + str(index)
    lab_vm.ssh(['sudo', 'tee', target], input=(BASE/name).read_bytes(), stdout=subprocess.DEVNULL)
    mapping[name if index < len(FILES) else 'scripts/bootstrap_restore_v0_1.sh'] = target
program = '''
import hashlib,json,os,shutil,subprocess,sys
sys.path.insert(0,'/lab')
from pathlib import Path
from setup_guest import guard
guard();os.umask(0o077)
root=Path('/lab/candidate-project')
receipt=json.loads(Path('/lab/input/input.json').read_text())
if not root.exists():
 subprocess.run(['git','clone','--no-hardlinks','/lab/input/git.git',str(root)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 subprocess.run(['git','-C',str(root),'checkout',receipt['git_commit']],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
else:
 previous=json.loads(Path('/lab/candidate.json').read_text())
 assert previous['git_commit']==subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
mapping=MAPPING
hashes={}
for relative,source in mapping.items():
 for target in (root/relative,root/'scripts/access_runtime/hc-router-backup-20261101-r15'/relative):
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
  hashes[target.relative_to(root).as_posix()]=hashlib.sha256(target.read_bytes()).hexdigest()
manifest=root/'EXPORT_MANIFEST.json';value=json.loads(manifest.read_text())
value['files']=[dict(row,sha256=hashlib.sha256((root/row['path']).read_bytes()).hexdigest()) for row in value['files'] if (root/row['path']).is_file()]
manifest.write_text(json.dumps(value,indent=2)+'\\n')
for key,val in [('user.name','HC isolated recovery audit'),('user.email','audit@localhost')]:
 subprocess.run(['git','-C',str(root),'config',key,val],check=True)
subprocess.run(['git','-C',str(root),'add','--all','--force','--','.'],check=True)
subprocess.run(['git','-C',str(root),'commit','-qm','Verify explicit recovery and export corrections in isolated lab'],check=True)
commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
if not Path('/lab/candidate.git').exists():
 subprocess.run(['git','clone','--bare','--no-hardlinks',str(root),'/lab/candidate.git'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
else:
 subprocess.run(['git','--git-dir','/lab/candidate.git','fetch',str(root),'HEAD'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
subprocess.run(['git','--git-dir','/lab/candidate.git','update-ref','refs/heads/recovery-candidate',commit],check=True)
subprocess.run(['git','--git-dir','/lab/candidate.git','symbolic-ref','HEAD','refs/heads/recovery-candidate'],check=True)
report={'git_commit':commit,'external_git_commit':receipt['git_commit'],'snapshot_id':receipt['snapshot_id'],'correction_sha256':hashes,'production_modified':False,'encrypted_bundle_modified':False}
Path('/lab/candidate.json').write_text(json.dumps(report,indent=2)+'\\n')
print(json.dumps(report))
'''.replace('MAPPING', repr(mapping))
lab_vm.ssh(['sudo', 'python3'], input=program, text=True)
