from pathlib import Path
import json,shutil,subprocess
B=Path('/srv/docker/homecontrol');P=Path('/tmp/hc41-44-20261029/image');P.mkdir(exist_ok=True)
base='homecontrol-backend:hc-read-models-20261028-r8'
actual=json.loads(subprocess.check_output(['docker','image','inspect',base]))[0]['Id']
assert actual=='sha256:75501094a45921cb9724b9f2082981e451d33be9f2ffc82706a33b61b137668c'
for p in (B/'infra/backend').glob('*.py'):shutil.copyfile(p,P/p.name)
shutil.copytree(B/'infra/backend/static',P/'static',dirs_exist_ok=True)
shutil.copyfile(B/'infra/backend/deployment_policy.json',P/'deployment_policy.json')
(P/'Dockerfile').write_text('FROM '+base+'\nUSER root\nCOPY *.py /app/\nCOPY static /app/static\nCOPY deployment_policy.json /app/deployment_policy.json\nRUN groupadd --gid 10001 homecontrol && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp homecontrol\nUSER 10001:10001\nENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp\n')
r=subprocess.run(['docker','build','--network','none','--pull=false','-t','hc44-backend-test:20261029',str(P)],capture_output=True,text=True)
(P.parent/'image-build.log').write_text(r.stdout+r.stderr)
if r.returncode:raise RuntimeError('Isolated image build failed')
image=json.loads(subprocess.check_output(['docker','image','inspect','hc44-backend-test:20261029']))[0]
(P.parent/'image.json').write_text(json.dumps({'image':image['Id'],'base':actual,'user':image['Config']['User'],'dependency_updates':False},indent=2)+'\n')
print(json.dumps({'image':image['Id'],'user':image['Config']['User']}))
