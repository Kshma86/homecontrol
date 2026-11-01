"""Read-only cloud smoke; run only after explicit Xiaomi-session-use approval."""
import json,os,shutil,subprocess,tempfile,urllib.request,uuid
from pathlib import Path
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-router-backup-20261101-r16'
def prepare_auth(source,target):
 # This copy requires real host permission, never a privileged container read.
 # The parent is root-only during a sudo run; only the test-container UID may
 # read the single file. The original root-owned credential remains untouched.
 with target.open('xb') as out:
  os.fchmod(out.fileno(),0o400)
  with source.open('rb') as inp:shutil.copyfileobj(inp,out)
  if os.geteuid()==0:os.fchown(out.fileno(),1000,1000)

def main():
 v=json.load(urllib.request.urlopen('http://127.0.0.1:5000/api/xiaomi-x10/cache',timeout=5))
 obj=None
 for collection in ('raw','topics'):
  values=v.get(collection,{})
  if isinstance(values,dict):
   for key,value in values.items():
    if key.endswith('/map/object_name') or key=='map/object_name':
     if isinstance(value,dict):value=value.get('payload',value.get('value'))
     if isinstance(value,str):obj=value
 if not obj:raise RuntimeError('No cached map object reference')
 code='''import contextlib,io,json,certifi
from pathlib import Path
from xiaomi_x10_map import XiaomiX10MapClient
with contextlib.redirect_stdout(io.StringIO()):
 c=XiaomiX10MapClient(output_dir='/tmp/map');c.load_auth('/auth')
 raw=c.download_object_bytes(Path('/object').read_text())
 parsed=json.loads(raw)
assert isinstance(parsed,dict) and raw
print(json.dumps({'ok':True,'cloud_tls_and_saved_session':True,'map_downloaded_and_json_decoded':True,'robot_commands_sent':False,'bytes':len(raw),'certifi':certifi.__version__}))
'''
 m=json.loads((K/'release.json').read_text())
 with tempfile.TemporaryDirectory(prefix='.x10-cloud-',dir=K/'private') as directory:
  auth=Path(directory)/'auth.json'
  fixture=Path(directory)/'object.txt';fixture.write_text(obj);fixture.chmod(0o400)
  if os.geteuid()==0:os.chown(fixture,1000,1000)
  original=B/'apps/xiaomi-x10/x10_maps/xiaomi_cloud_auth.json'
  if original.is_symlink():raise ValueError('Credential symlink refused')
  prepare_auth(original,auth)
  name='hc-r13-cloud-smoke-'+uuid.uuid4().hex
  try:
   r=subprocess.run(['docker','run','--rm','--name',name,'--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=32m','-v',str(auth)+':/auth:ro','-v',str(fixture)+':/object:ro','--entrypoint','python',m['images']['homecontrol-xiaomi-x10'],'-B','-c',code],capture_output=True,text=True,timeout=90)
  finally:
   subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
 if r.returncode:
  path=K/'private'/('x10-smoke-error-'+uuid.uuid4().hex+'.log')
  with path.open('x') as log:os.fchmod(log.fileno(),0o600);log.write(r.stdout+r.stderr)
  raise RuntimeError('Candidate X10 cloud smoke failed; private log only')
 result=json.loads(r.stdout);(K/'evidence/x10-cloud.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
