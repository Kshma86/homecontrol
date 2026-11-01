"""Prepare local HC-12/32/23/43 candidate contexts; never deploy or read secrets.

The immutable active image is the compatibility baseline. Security wheels are
downloaded separately, hashed and installed offline. Full resulting package
versions are checked against requirements.lock. OS/HA upgrades remain separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/audit-evidence/hc32-23-43-20261031'
TARGET = ROOT / 'backups/releases/hc-f10-20261031-candidate'
COMPONENTS = {'backend':'infra/backend', 'ingest':'apps/hc_ingest',
              'tuya-poller':'apps/tuya-poller', 'gree-climate':'apps/gree-climate',
              'xiaomi-x10':'apps/xiaomi-x10', 'ha-growatt-poller':'apps/ha-growatt-poller',
              'ai-server':'apps/ai-server'}
PATCHES = {'flask':'3.1.3', 'pillow':'13.0.0', 'pip':'26.2.2', 'setuptools':'84.2.1',
           'urllib3':'2.8.0', 'requests':'2.34.2', 'certifi':'2026.10.18', 'werkzeug':'3.1.9'}


def run(args):
    return subprocess.check_output(args, text=True, timeout=180)


def normalized(name):
    return name.lower().replace('_','-').replace('.','-')


def source_files(name, folder):
    files = [p for p in (ROOT/folder).glob('*.py') if not p.name.startswith('test_')]
    if name == 'ai-server':
        files += [ROOT/'infra/backend/ai_domain_replies.py', ROOT/'infra/backend/ai_context_plan.py']
    return files


def health_recipe(name):
    if name in ('tuya-poller','gree-climate','xiaomi-x10','ha-growatt-poller'):
        return 'HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "worker_health.py", "--mode", "live"]\n'
    if name == 'backend':
        return 'HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "backend_healthcheck.py", "--mode", "workers"]\n'
    if name == 'ai-server':
        return 'HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen(\'http://127.0.0.1:8088/health/live\', timeout=2).close()"]\n'
    return ''


def prepare():
    if TARGET.exists():
        raise SystemExit('Candidate directory already exists; do not overwrite a tested context')
    before = json.loads((EVIDENCE / 'before.json').read_text())
    manifest = {'status':'prepared_not_deployed', 'components':{}, 'os_updated':False,
                'homeassistant_updated':False, 'remote_ai_excluded':True}
    for name, folder in COMPONENTS.items():
        container = 'homecontrol-' + name
        base = before['containers'][container]['image']
        tag = 'hc-f10-base-' + name + ':' + base.split(':')[1][:16]
        actual = run(['docker','image','inspect',base,'--format','{{.Id}}']).strip()
        if actual != base:
            raise RuntimeError('base image mismatch')
        # New isolated tag only; active release tags are never moved.
        subprocess.run(['docker','tag',base,tag],check=True)
        context = TARGET / name
        source = context / 'source'
        source.mkdir(parents=True)
        files = source_files(name, folder)
        for path in files:
            shutil.copyfile(path, source/path.name)
        packages = {normalized(n):v for n,v in before['python'][container]}
        changes = {n:v for n,v in PATCHES.items() if n in packages and packages[n] != v}
        packages.update(changes)
        lock = ''.join(f'{n}=={v}\n' for n,v in sorted(packages.items()))
        (context/'requirements.lock').write_text(lock)
        (ROOT/folder/'requirements.lock').write_text(lock)
        (context/'security.in').write_text(''.join(f'{n}=={v}\n' for n,v in sorted(changes.items())))
        (context/'wheels').mkdir()
        user = '10001:10001' if name == 'backend' else 'root'
        health = health_recipe(name)
        recipe = (f'FROM {tag}\nUSER root\nWORKDIR /app\n'
                  'COPY wheels /opt/hc-wheels\nCOPY security.lock /opt/hc-security.lock\n'
                  'RUN python -m pip install --no-index --no-deps --require-hashes --find-links=/opt/hc-wheels -r /opt/hc-security.lock && python -m pip check\n'
                  'COPY source/ /app/\nCOPY requirements.lock /app/requirements.lock\n' + health + f'USER {user}\n')
        (context/'Dockerfile').write_text(recipe)
        manifest['components'][name] = {'base_image':base,'base_tag':tag,
            'candidate_tag':'hc-f10-' + name + ':20261031-candidate', 'folder':folder,
            'packages':packages, 'security_changes':changes,
            'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}}
    TARGET.mkdir(exist_ok=True)
    (TARGET/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'prepared':len(manifest['components']),'deployed':False}))


def seal(name):
    manifest = json.loads((TARGET/'manifest.json').read_text())
    item = manifest['components'][name]
    context = TARGET/name
    wheels = list((context/'wheels').glob('*.whl'))
    lines = []
    for package, version in sorted(item['security_changes'].items()):
        candidates = [p for p in wheels if normalized(p.name.split('-')[0]) == package and p.name.split('-')[1] == version]
        if len(candidates) != 1:
            raise RuntimeError('exactly one wheel required: ' + package)
        digest = hashlib.sha256(candidates[0].read_bytes()).hexdigest()
        lines.append(f'{package}=={version} --hash=sha256:{digest}\n')
    (context/'security.lock').write_text(''.join(lines))
    (ROOT/item['folder']/'requirements.security.lock').write_text(''.join(lines))
    print(json.dumps({'sealed_component':name,'wheels':len(wheels)}))


def refresh():
    """Explicitly invalidate previous verification before restaging local edits."""
    manifest = json.loads((TARGET/'manifest.json').read_text())
    manifest['status'] = 'prepared_not_deployed'
    manifest.pop('verified_images', None)
    for name, item in manifest['components'].items():
        source = TARGET/name/'source'
        for path in source_files(name, item['folder']):
            shutil.copyfile(path, source/path.name)
        item['source_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
        recipe = TARGET/name/'Dockerfile'
        lines = [line for line in recipe.read_text().splitlines() if not line.startswith('HEALTHCHECK ')]
        lines.insert(-1, health_recipe(name).rstrip())
        recipe.write_text('\n'.join(line for line in lines if line)+'\n')
    (TARGET/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'refreshed':len(manifest['components']),'previous_verification_invalidated':True}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','seal','refresh'))
    parser.add_argument('--component',choices=tuple(COMPONENTS))
    args=parser.parse_args()
    if args.action=='prepare':
        prepare()
    elif args.action=='refresh':
        refresh()
    elif args.component:
        seal(args.component)
    else:
        parser.error('--component required for seal')
