"""Verify baked public code and exact installed-package parity with the live bases."""
import hashlib,json,subprocess
from pathlib import Path
from prepare import BASE,KIT,COMPONENTS,digest,read,write
code='''import hashlib,importlib.metadata as m,json,sys
from pathlib import Path
names=json.load(sys.stdin)
print(json.dumps({'packages':sorted((d.metadata.get('Name',''),d.version) for d in m.distributions()),'code':{n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest() if (Path('/app')/n).exists() else None for n in names}}))
'''
def inspect(image,names):
 args=['docker','run','--rm','-i','--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--entrypoint','python',image,'-B','-c',code]
 return json.loads(subprocess.run(args,input=json.dumps(names),capture_output=True,text=True,check=True).stdout)
def main():
 m=read(KIT/'release.json');out={}
 for service,(folder,container) in COMPONENTS.items():
  root=KIT/'source'/folder
  names=[p.name for p in root.glob('*.py')] if service=='backend' else [('mdns_responder.py' if service=='mdns' else 'ha_growatt_poller.py')]
  if service=='backend':names+=['deployment_policy.json','repository_service.py']
  before=inspect(m['baseline'][container]['image'],names);after=inspect(m['images'][service],names)
  assert before['packages']==after['packages'],service
  for n in names:
   if n=='repository_service.py':assert after['code'][n] is None;continue
   assert after['code'][n]==digest(root/n),(service,n)
  out[service]={'ok':True,'image':m['images'][service],'base_image':m['baseline'][container]['image'],'packages_unchanged':True,'package_count':len(after['packages']),'baked_code_sha256':after['code']}
 write(KIT/'evidence/baked-code-and-packages.json',{'ok':True,'components':out,'network':'none','production_changed':False})
 print(json.dumps({'ok':True,'components':len(out)}))
if __name__=='__main__':main()
