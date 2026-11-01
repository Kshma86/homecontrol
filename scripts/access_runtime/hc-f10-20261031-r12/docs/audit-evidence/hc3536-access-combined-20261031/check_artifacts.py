from pathlib import Path
import json,hashlib,subprocess,sys,re
B=Path('/srv/docker/homecontrol');K=B/'backups/releases/hc-f10-20261031-r12';S=K/'source';W=Path('/tmp/hc-access-combined-20261031')
sys.path.insert(0,str(B/'scripts/access_release'));from prepare import BACKEND_FILES,APPS
m=json.loads((K/'release.json').read_text())
specs={'backend':('infra/backend',BACKEND_FILES)};specs.update({service:('apps/'+folder,names) for service,(folder,names) in APPS.items()})
for service,(directory,names) in specs.items():
 script='import hashlib,json;from pathlib import Path;print(json.dumps({n:hashlib.sha256((Path("/app")/n).read_bytes()).hexdigest() for n in '+repr(list(names))+'}))'
 r=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--entrypoint','python',m['images'][service],'-c',script],capture_output=True,text=True,check=True)
 expected={n:hashlib.sha256((S/directory/n).read_bytes()).hexdigest() for n in names}
 assert json.loads(r.stdout)==expected,service
script='import app; b=app.get_process_binding_service(); p=app.get_power_wall_service();assert b.climate_fan_coordinator is p.climate_fan_coordinator is app._climate_fan_coordinator;assert type(b.ai_power_coordinator).__name__=="ScopedAiPowerCoordinator";print("shared climate coordinator and scoped AI coordinator present")'
r=subprocess.run(['docker','run','--rm','--network','none','--read-only','--tmpfs','/tmp:rw,size=32m','-e','HC_BACKUP_DIR=/tmp/backups','-e','HC_AI_STATE_DIR=/tmp/ai-state','--entrypoint','python',m['images']['backend'],'-c',script],capture_output=True,text=True)
if r.returncode:
 (W/'private/artifact-error.log').write_text(r.stderr);raise RuntimeError('Actual image coordinator wiring check failed')
name='hc-combined-frontend-smoke';created=False
try:
 assert subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0
 subprocess.run(['docker','run','-d','--name',name,'--network','none','--add-host','backend:127.0.0.1',m['images']['frontend']],capture_output=True,check=True);created=True
 import time;time.sleep(.3)
 dist=W/'frontend-dist';index=hashlib.sha256((dist/'index.html').read_bytes()).hexdigest()
 asset=next((dist/'assets').glob('HcAdmin-*.js'));asset_sha=hashlib.sha256(asset.read_bytes()).hexdigest()
 script='import urllib.request,hashlib;assert hashlib.sha256(urllib.request.urlopen("http://127.0.0.1:3000/",timeout=3).read()).hexdigest()=='+repr(index)+';assert hashlib.sha256(urllib.request.urlopen("http://127.0.0.1:3000/assets/'+asset.name+'",timeout=3).read()).hexdigest()=='+repr(asset_sha)
 subprocess.run(['docker','run','--rm','--network','container:'+name,'--read-only','--cap-drop','ALL','--entrypoint','python',m['images']['backend'],'-c',script],capture_output=True,check=True)
finally:
 if created:subprocess.run(['docker','rm','-f',name],capture_output=True)
result={'ok':True,'python_images_match_frozen_sources':len(specs),'hc3536_shared_coordinator_in_actual_backend_image':True,'hc44_scoped_ai_coordination_preserved':True,'actual_frontend_http_index_and_hc_admin_asset_match_build':True,'production_used':False,'network_none':True,'dependency_updates':False}
(W/'evidence/image-source-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
