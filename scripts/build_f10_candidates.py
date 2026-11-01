"""Build separate F10 candidates. No deployment actions; logs contain public dependencies only."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
target=root/'backups/releases/hc-f10-20261031-candidate'
evidence=root/'docs/audit-evidence/hc32-23-43-20261031'
def build(pair):
    name,item=pair
    context=target/name
    start=time.monotonic()
    with (evidence/(name+'-build.log')).open('w') as log:
        actual=subprocess.check_output(['docker','image','inspect',item['base_tag'],'--format','{{.Id}}'],text=True).strip()
        if actual!=item['base_image']:raise RuntimeError('base tag changed')
        download=['docker','run','--rm','--network','bridge','--read-only','--user','1000:1000',
          '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','512m','--cpus','1',
          '--tmpfs','/tmp:rw,nosuid,nodev,size=256m','-e','HOME=/tmp','-e','PIP_CONFIG_FILE=/dev/null',
          '--mount',f'type=bind,src={context},dst=/out',item['base_image'],
          'python','-m','pip','download','--disable-pip-version-check','--no-deps','--only-binary=:all:',
          '--index-url','https://pypi.org/simple','--dest','/out/wheels','-r','/out/security.in']
        result=subprocess.run(download,stdout=log,stderr=log,timeout=240)
        if result.returncode:
            return name,{'download_exit':result.returncode}
        result=subprocess.run(['python3',str(root/'scripts/prepare_f10_candidates.py'),'seal','--component',name],stdout=log,stderr=log,timeout=30)
        if result.returncode:
            return name,{'seal_exit':result.returncode}
        result=subprocess.run(['docker','build','--pull=false','--network','none','--tag',item['candidate_tag'],str(context)],stdout=log,stderr=log,timeout=300)
        if result.returncode:
            return name,{'build_exit':result.returncode}
        image=subprocess.check_output(['docker','image','inspect',item['candidate_tag'],'--format','{{.Id}}'],text=True).strip()
        return name,{'image':image,'seconds':round(time.monotonic()-start,1),'success':True}


def main():
    manifest=json.loads((target/'manifest.json').read_text())
    manifest['status']='prepared_not_deployed'
    manifest.pop('verified_images',None)
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    previous_path=evidence/'build-results.json'
    previous=json.loads(previous_path.read_text()) if previous_path.exists() else {}
    results={name:row for name,row in previous.items() if name not in manifest['components']}
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        for name,result in pool.map(build,manifest['components'].items()):
            results[name]=result
            print(json.dumps({name:result}),flush=True)
            (evidence/'build-results.json').write_text(json.dumps(results,indent=2)+'\n')
    if not all(row.get('success') for row in results.values()):raise SystemExit(1)


if __name__=="__main__":main()
