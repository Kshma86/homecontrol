#!/usr/bin/env python3
"""Prepare a sealed r14 backup release from active r13; never performs a cutover."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

BASE = Path('/srv/docker/homecontrol')
OLD = 'hc-f10-20261031-r13'
NAME = 'hc-router-backup-20261101-r14'
KIT = BASE / 'backups/releases' / NAME

FILES = (
    'infra/backend/router_backup.py', 'infra/backend/deployment_policy.py',
    'infra/backend/backup_service.py', 'infra/backend/backup_export.py', 'infra/backend/backup_export_manifest.py',
    'infra/backend/tests/test_deployment_policy.py',
    'scripts/backup_runner_impl.py', 'scripts/hostops/backup_runner.py',
    'scripts/backup_archive_worker.sh', 'scripts/backup_weekly_worker.sh',
    'scripts/backup_check_worker.sh', 'scripts/backup_config_sync_worker.sh', 'scripts/backup_offsite_worker.sh',
    'scripts/deployment_policy_cli.py', 'scripts/router_restic.py', 'scripts/configure_router_backup.py',
    'scripts/install_router_backup_prereqs.py', 'scripts/restore_smoke.py', 'scripts/bootstrap_restore_v0_1.sh',
    'scripts/tests/test_router_backup.py', 'scripts/router_release/activate.py', 'scripts/router_release/prepare.py',
    'scripts/router_release/test_activate.py',
    'infra/frontend/src/features/backup/Backup.jsx', 'infra/frontend/src/features/backup/backupJobState.mjs',
    'infra/frontend/tests/backup-jobs.test.mjs',
    'docs/router-ftp-backup-implementation.md', 'docs/router-ftp-backup-plan.md',
)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(part)
    return value.hexdigest()


def call(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected release source context: ' + old[:70])
    return text.replace(old, new)


def source():
    if KIT.exists():
        raise ValueError('Release already exists; inspect rather than overwrite')
    prior = BASE / 'backups/releases' / OLD
    manifest = json.loads((prior / 'release.json').read_text())
    if json.loads((BASE / 'infra/access-release.json').read_text())['release'] != OLD:
        raise ValueError('Active release changed')
    rows = json.loads(subprocess.check_output(['docker', 'inspect', *manifest['baseline']]))
    KIT.mkdir()
    (KIT / 'private').mkdir(mode=0o700)
    (KIT / 'evidence').mkdir()
    (KIT / 'tools').mkdir()
    target = KIT / 'source'
    shutil.copytree(prior / 'source', target, ignore=shutil.ignore_patterns('__pycache__'))
    # Reuse the reviewed runtime, including r13 X10 and all unrelated fixes.
    for path in target.rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.sh', '.service', '.timer', '.path', '.conf', '.json'):
            text = path.read_text()
            if OLD in text:
                path.write_text(text.replace(OLD, NAME))
    for name in FILES:
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASE / name, out)
    bootstrap = target / 'scripts/bootstrap_restore_v0_1.sh'
    bootstrap.write_text(bootstrap.read_text().replace(OLD, NAME))
    policy = json.loads((target / 'infra/backend/deployment_policy.json').read_text())
    policy['backup_profile'] = 'router-ftp'
    (target / 'infra/backend/deployment_policy.json').write_text(json.dumps(policy, indent=2) + '\n')
    deploy = target / 'scripts/f10_release/deploy.py'
    text = deploy.read_text()
    text = replace_once(text, "OLD='hc-f10-20261031-r12'", 'OLD=' + repr(OLD))
    text = replace_once(text, 'timeout=180, **kwargs):', 'timeout=180, extra_env=None, **kwargs):')
    text = replace_once(text, "    env['DOCKER_HOST']='unix:///var/run/docker.sock'", "    env.update(extra_env or {})\n    env['DOCKER_HOST']='unix:///var/run/docker.sock'")
    text = replace_once(text, "        paths.extend((BASE/'apps/xiaomi-x10/x10_maps').glob('xiaomi_cloud_auth*.json'))", """        paths.extend((BASE/'apps/xiaomi-x10/x10_maps').glob('xiaomi_cloud_auth*.json'))
        router = globals().get('ROUTER_SETTINGS')
        if router:
            paths.extend(Path(router[key]) for key in ('router_rclone_config','restic_password_file'))""")
    text = replace_once(text, "        for file in runtime.rglob('*'):", """        if globals().get('ROUTER_SETTINGS'):
            target = root/'srv/docker/homecontrol/backups/backup_settings.json'
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(ROUTER_SETTINGS)+'\\n');target.chmod(0o600)
        for file in runtime.rglob('*'):""")
    deploy.write_text(text)
    tests = target / 'scripts/f10_release/test_deploy.py'
    text = tests.read_text().replace("expected={'backend','homecontrol-xiaomi-x10'}", "expected={'backend','frontend'}")
    tests.write_text(text)
    model = json.loads((BASE / 'infra/docker-compose.yml').read_text())
    for name in ('backend', 'frontend'):
        service = model['services'][name]
        for entry in service.get('env_file', []):
            entry['path'] = entry['path'].replace('/' + OLD + '/', '/' + NAME + '/')
        for entry in service.get('volumes', []):
            entry['source'] = entry['source'].replace('/' + OLD + '/', '/' + NAME + '/')
    (target / 'runtime.compose.json').write_text(json.dumps(model, indent=2) + '\n')
    manifest.update(release=NAME, previous_release=OLD, changed_services=['backend', 'frontend'],
                    previous_compose_sha256=digest(BASE / 'infra/docker-compose.yml'),
                    baseline={row['Name'].lstrip('/'): {'id': row['Id'], 'image': row['Image']} for row in rows},
                    source_sha256={}, acceptance_sha256=None, ready_for_root_deploy=False,
                    scope=['Encrypted router FTP backup; external Git; AI remains isolated'],
                    status='preparing_router_backup_not_deployed', deployed=False)
    (KIT / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    tool = Path('/tmp/hc-router-test-bin/rclone')
    if not tool.is_file():
        raise ValueError('Verified rclone test binary is missing')
    shutil.copyfile(tool, KIT / 'tools/rclone')
    (KIT / 'tools/rclone').chmod(0o755)
    shutil.copytree(BASE / 'docs/audit-evidence/router-ftp-20261101', KIT / 'evidence/source-tests')


def build():
    manifest = json.loads((KIT / 'release.json').read_text())
    contexts = KIT / 'images'
    contexts.mkdir()
    backend = contexts / 'backend'; backend.mkdir()
    modules = backend / 'modules'; modules.mkdir()
    for name in ('router_backup.py', 'deployment_policy.py', 'deployment_policy.json',
                 'backup_service.py', 'backup_export.py', 'backup_export_manifest.py'):
        shutil.copyfile(KIT / 'source/infra/backend' / name, modules / name)
    base_tag = 'hc-router-backend-base:r13'
    call(['docker', 'image', 'tag', manifest['images']['backend'], base_tag])
    (backend / 'Dockerfile').write_text('FROM ' + base_tag + '\nCOPY modules/ /app/\n')
    frontend = contexts / 'frontend'; frontend.mkdir()
    dist = Path('/tmp/hc-router-ui-build/dist')
    if not (dist / 'index.html').is_file():
        raise ValueError('Tested frontend build is missing')
    shutil.copytree(dist, frontend / 'dist')
    base_tag = 'hc-router-frontend-base:r13'
    call(['docker', 'image', 'tag', manifest['images']['frontend'], base_tag])
    (frontend / 'Dockerfile').write_text('FROM ' + base_tag + '\nCOPY dist/ /usr/share/nginx/html/\n')
    model_path = KIT / 'source/runtime.compose.json'
    model = json.loads(model_path.read_text())
    for service, context in (('backend', backend), ('frontend', frontend)):
        tag = 'hc-router-' + service + ':20261101-r14'
        call(['docker', 'build', '--pull=false', '--network=none', '-t', tag, str(context)])
        image = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
        manifest['images'][service] = image
        model['services'][service]['image'] = image
    model_path.write_text(json.dumps(model, indent=2) + '\n')
    images = sorted(set(manifest['recovery_images']) | set(manifest['images'].values()))
    output = KIT / 'private/access-images.tar.gz'
    with output.open('xb') as stream:
        process = subprocess.Popen(['docker', 'image', 'save', *images], stdout=subprocess.PIPE)
        with gzip.GzipFile(filename='', mode='wb', compresslevel=1, fileobj=stream, mtime=0) as zipped:
            shutil.copyfileobj(process.stdout, zipped, 1024 * 1024)
        process.stdout.close()
        if process.wait():
            raise RuntimeError('Offline image save failed')
    output.chmod(0o600)
    manifest.update(recovery_images=images, offline_image_archive_sha256=digest(output),
                    rclone_sha256=digest(KIT / 'tools/rclone'))
    (KIT / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')


def seal():
    manifest = json.loads((KIT / 'release.json').read_text())
    if (KIT / 'private/transition').exists():
        raise ValueError('Cannot reseal after cutover')
    required = ('installer-tests.log', 'router-activation-tests.log', 'baked-router-tests.log', 'offline-load.log')
    for name in required:
        text = (KIT / 'evidence' / name).read_text()
        if name.endswith('tests.log') and '\nOK' not in text:
            raise ValueError('Test evidence not successful: ' + name)
        if name == 'offline-load.log' and 'Loaded image' not in text:
            raise ValueError('Offline images not loaded successfully')
    report = {'ok': True, 'release': NAME, 'scope': manifest['scope'],
              'router_runtime_test': 'pending local FTP password', 'deployed': False,
              'evidence_sha256': {str(path.relative_to(KIT / 'evidence')): digest(path)
                                  for path in (KIT / 'evidence').rglob('*') if path.is_file() and path.name != 'acceptance.json'}}
    (KIT / 'evidence/acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    for path in (KIT / 'source').rglob('__pycache__'):
        shutil.rmtree(path)
    manifest.update(source_sha256={str(path.relative_to(KIT / 'source')): digest(path)
                                   for path in (KIT / 'source').rglob('*') if path.is_file()},
                    acceptance_sha256=digest(KIT / 'evidence/acceptance.json'), ready_for_root_deploy=True,
                    status='router_release_ready_local_sudo_and_ftp_password_required')
    (KIT / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'release': NAME, 'ready': True, 'deployed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('source', 'build', 'seal'))
    args = parser.parse_args()
    {'source': source, 'build': build, 'seal': seal}[args.action]()
