"""Read-only candidate integrity/package verification. This command cannot deploy."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'backups/releases/hc-f10-20261031-candidate'
OUT=ROOT/'docs/audit-evidence/hc32-23-43-20261031'


def run(args):
    return subprocess.check_output(args,text=True,timeout=60)


def main():
    manifest=json.loads((TARGET/'manifest.json').read_text())
    builds=json.loads((OUT/'build-results.json').read_text())
    inventories={}
    for name,item in manifest['components'].items():
        expected_lock=''.join(f'{n}=={v}\n' for n,v in sorted(item['packages'].items()))
        for lock in (ROOT/item['folder']/'requirements.lock', TARGET/name/'requirements.lock'):
            if lock.read_text()!=expected_lock:
                raise RuntimeError('full lock file changed: '+str(lock))
        if (ROOT/item['folder']/'requirements.security.lock').read_bytes()!=(TARGET/name/'security.lock').read_bytes():
            raise RuntimeError('security lock file changed: '+name)
        image=builds[name]['image']
        if run(['docker','image','inspect',item['candidate_tag'],'--format','{{.Id}}']).strip()!=image:
            raise RuntimeError('candidate tag changed: '+name)
        for relative,digest in item['source_sha256'].items():
            staged=TARGET/name/'source'/relative
            if hashlib.sha256(staged.read_bytes()).hexdigest()!=digest:
                raise RuntimeError('candidate source changed: '+name+'/'+relative)
            paths=[ROOT/item['folder']/relative]
            if name=='ai-server' and relative in ('ai_domain_replies.py','ai_context_plan.py'):
                paths=[ROOT/'infra/backend'/relative]
            if not paths[0].exists() or hashlib.sha256(paths[0].read_bytes()).hexdigest()!=digest:
                raise RuntimeError('worktree source differs from candidate: '+str(paths[0]))
        for line in (TARGET/name/'security.lock').read_text().splitlines():
            requirement,expected=line.split(' --hash=sha256:')
            package,version=requirement.split('==')
            wheels=[p for p in (TARGET/name/'wheels').glob('*.whl')
                    if p.name.split('-')[0].lower().replace('_','-')==package
                    and p.name.split('-')[1]==version]
            if len(wheels)!=1 or hashlib.sha256(wheels[0].read_bytes()).hexdigest()!=expected:
                raise RuntimeError('security wheel mismatch: '+name+'/'+package)
        args=['docker','run','--rm','--network','none','--read-only','--user','1000:1000',
              '--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,size=32m',
              '--env','HOME=/tmp',image]
        code="import importlib.metadata,json;print(json.dumps(sorted({(d.metadata['Name'],d.version) for d in importlib.metadata.distributions()})))"
        rows=json.loads(run(args+['python','-B','-c',code]))
        source_code=('import hashlib,json;from pathlib import Path;files='
                     +repr(sorted(item['source_sha256']))
                     +';print(json.dumps({n:hashlib.sha256((Path("/app")/n).read_bytes()).hexdigest() for n in files}))')
        if json.loads(run(args+['python','-B','-c',source_code]))!=item['source_sha256']:
            raise RuntimeError('baked image source differs from staged source: '+name)
        actual={n.lower().replace('_','-').replace('.','-'):v for n,v in rows}
        if actual!=item['packages']:
            raise RuntimeError('full dependency lock mismatch: '+name)
        check=run(args+['python','-B','-m','pip','check'])
        if 'No broken requirements found' not in check:
            raise RuntimeError('dependency incompatibility: '+name)
        inventories['homecontrol-'+name]=rows
    # AI SSD restriction must survive the candidate build.
    image=builds['backend']['image']
    policy=json.loads(run(['docker','run','--rm','--network','none','--read-only',image,
        'python','-B','-c','import deployment_policy,json; p=deployment_policy.policy(); print(json.dumps({k:p[k] for k in ("restricted","valid")}))']))
    if policy!={'restricted':True,'valid':True}:
        raise RuntimeError('AI isolation policy changed')
    front=manifest['frontend']
    if run(['docker','image','inspect',front['candidate_tag'],'--format','{{.Id}}']).strip()!=front['image']:
        raise RuntimeError('frontend tag changed')
    if hashlib.sha256((ROOT/'infra/frontend/package-lock.json').read_bytes()).hexdigest()!=front['package_lock_sha256']:
        raise RuntimeError('frontend lock changed')
    if (ROOT/'infra/frontend/package.json').read_bytes()!=(TARGET/'frontend/package.json').read_bytes():
        raise RuntimeError('frontend package definitions differ')
    base=['docker','run','--rm','--network','none','--read-only']
    paths=['/usr/share/nginx/html/'+p.removeprefix('dist/') for p in sorted(front['dist_sha256'])]
    baked=run(base+['--entrypoint','sha256sum',front['image'],*paths])
    expected={p:front['dist_sha256']['dist/'+p.removeprefix('/usr/share/nginx/html/')] for p in paths}
    actual={line.split(None,1)[1]:line.split(None,1)[0] for line in baked.splitlines()}
    if actual!=expected:
        raise RuntimeError('frontend baked assets changed')
    inventory=set(run(base+['--entrypoint','find',front['image'],'/usr/share/nginx/html','-type','f']).splitlines())
    if inventory!=set(paths):
        raise RuntimeError('obsolete or extra frontend assets remain')
    (OUT/'python-candidate.json').write_text(json.dumps(inventories,indent=2)+'\n')
    result={'python_candidates':len(inventories),'frontend_assets_match':True,'no_obsolete_frontend_assets':True,
            'source_and_wheel_integrity':True,
            'full_dependency_locks_match':True,'pip_check':True,'ai_isolation_preserved':True,
            'deployed':False}
    (OUT/'candidate-integrity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
