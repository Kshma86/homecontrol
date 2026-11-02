"""Read authorized operator export; count tar sizes without extracting archive data."""
import collections,hashlib,io,json,os,subprocess,tarfile
from pathlib import Path
INPUT=Path('/tmp/hc-security-audit-20261102/input')
PRIVATE=Path('/tmp/hc23-closure-20261102/capacity');PRIVATE.mkdir(mode=0o700,exist_ok=True)
os.umask(0o077)
assert INPUT.stat().st_uid==os.getuid() and not INPUT.stat().st_mode&0o077
settings=json.loads((INPUT/'router-settings.json').read_text());receipt=json.loads((INPUT/'input.json').read_text())
encrypted=subprocess.check_output(['git','--git-dir',str(INPUT/'git.git'),'show',receipt['git_commit']+':secrets/homecontrol-secrets-latest.tar.gz.age'])
assert hashlib.sha256(encrypted).hexdigest()==receipt['git_bundle_sha256']
keydata=subprocess.run(['age','-d','-i',str(INPUT/'age-key.txt')],input=encrypted,capture_output=True,check=True).stdout
with tarfile.open(fileobj=io.BytesIO(keydata),mode='r:gz') as bundle:
 members=[m for m in bundle if m.isfile() and m.name.removeprefix('./').endswith(settings['restic_password_file'].lstrip('/'))]
 assert len(members)==1 and members[0].size<65536
 password=PRIVATE/'restic-password';password.write_bytes(bundle.extractfile(members[0]).read());password.chmod(0o600)
try:
 command=['restic','--no-lock','-r',str(INPUT/'repository'),'--password-file',str(password)]
 result=subprocess.run(command+['ls','--json',receipt['snapshot_id']],capture_output=True,text=True,check=True)
 nodes=[json.loads(line) for line in result.stdout.splitlines()]
 paths=[x['path'] for x in nodes if x.get('type')=='file' and x.get('name')==receipt['archive_receipt']['name']]
 assert len(paths)==1
 p=subprocess.Popen(command+['dump',receipt['snapshot_id'],paths[0]],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 totals=collections.Counter();large=[];count=0
 with tarfile.open(fileobj=p.stdout,mode='r|gz') as archive:
  for member in archive:
   if not member.isfile():continue
   count+=1;parts=Path(member.name).parts
   # Public categories only; never export file data or credential paths.
   group='runtime_images' if 'access-images.tar.gz' in parts else 'other_files'
   totals[group]+=member.size
   if member.name.endswith('/access-images.tar.gz'):large.append({'release':parts[-3],'bytes':member.size})
 assert p.wait()==0
 report={'ok':True,'snapshot_id':receipt['snapshot_id'],'compressed_archive_bytes':receipt['archive_receipt']['size_bytes'],
 'regular_files':count,'expanded_regular_file_bytes':sum(totals.values()),'groups':dict(totals),'image_archives':large,
 'data_extracted':False,'remote_write_commands':0,'private_inventory_uploaded':False}
 out=Path(__file__).resolve().parent/'archive-capacity.json';out.write_text(json.dumps(report,indent=2)+'\n');out.chmod(0o644)
 print(json.dumps(report))
finally:password.unlink(missing_ok=True)
