"""Fetch public stable-release and OCI manifest metadata only; never pull/run AI."""
from datetime import datetime, timezone
import hashlib,json,re
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
OUT=Path(__file__).resolve().parent
ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'
def get(url,headers=None):
 with urlopen(Request(url,headers={'User-Agent':'HC audit metadata verifier',**(headers or {})}),timeout=30) as r:return r.read(),dict(r.headers)
def data(url):return json.loads(get(url)[0])
releases={
 'ollama':data('https://api.github.com/repos/ollama/ollama/releases/latest'),
 'open-webui':data('https://api.github.com/repos/open-webui/open-webui/releases/latest'),
 'gitea':data('https://dl.gitea.com/gitea/version.json')}
(OUT/'dormant-release-metadata.json').write_text(json.dumps(releases,indent=2)+'\n')
print({k:(v.get('tag_name') if isinstance(v,dict) else v) for k,v in releases.items()},flush=True)
gitea=releases['gitea'];gitea=gitea.get('latest') or gitea.get('version')
gitea=gitea.get('version') if isinstance(gitea,dict) else gitea
assert isinstance(gitea,str) and re.fullmatch(r'v?\d+\.\d+\.\d+',gitea)
refs={'ollama':('registry-1.docker.io','ollama/ollama',releases['ollama']['tag_name'].removeprefix('v'),'ollama/ollama'),
 'open-webui':('ghcr.io','open-webui/open-webui',releases['open-webui']['tag_name'],'ghcr.io/open-webui/open-webui'),
 'gitea':('registry-1.docker.io','gitea/gitea',gitea.removeprefix('v'),'gitea/gitea')}
rows={}
for name,(registry,repo,tag,public) in refs.items():
 url='https://'+registry+'/v2/'+repo+'/manifests/'+tag
 headers={'Accept':ACCEPT}
 try:raw,response=get(url,headers)
 except HTTPError as e:
  if e.code!=401:raise
  challenge=e.headers['WWW-Authenticate'];params=dict(re.findall(r'(\w+)="([^"]*)"',challenge))
  token=data(params['realm']+'?'+urlencode({k:params[k] for k in ('service','scope') if k in params}))
  headers['Authorization']='Bearer '+(token.get('token') or token['access_token'])
  raw,response=get(url,headers)
 digest='sha256:'+hashlib.sha256(raw).hexdigest()
 given=next((v for k,v in response.items() if k.lower()=='docker-content-digest'),None)
 assert given==digest
 manifest=json.loads(raw)
 platforms=[m.get('platform') for m in manifest.get('manifests',[]) if m.get('platform',{}).get('architecture')=='amd64' and m.get('platform',{}).get('os')=='linux']
 assert platforms or manifest.get('config'),name
 rows[name]=dict(source_version=tag,image=public+'@'+digest,manifest_digest=digest,linux_amd64=bool(platforms),metadata_url=url,manifest_bytes=len(raw),status='dormant_metadata_pinned_not_started_or_runtime_qualified')
 (OUT/(name+'-oci-manifest.json')).write_bytes(raw)
 print(name,tag,digest,flush=True)
(OUT/'dormant-image-pins.json').write_text(json.dumps(dict(checked_at=datetime.now(timezone.utc).isoformat(),images=rows,ai_enabled=False,images_pulled=0,containers_started=0),indent=2)+'\n')
