"""Prepare the FTP idle-pool correction as a new release; never deploy."""
import ast
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

BASE = Path('/srv/docker/homecontrol')
PRIOR = 'hc-audit-20261102-r21'
NAME = 'hc-audit-20261103-r22'
KIT = BASE / 'backups/releases' / NAME
PREVIOUS = BASE / 'backups/releases' / PRIOR


def read(path): return json.loads(Path(path).read_text())
def write(path, value): Path(path).write_text(json.dumps(value, indent=2) + '\n')
def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''): h.update(block)
    return h.hexdigest()


def source():
    assert not KIT.exists(), 'Never overwrite a release'
    m = read(PREVIOUS / 'release.json')
    assert sha(PREVIOUS / 'release.json') == 'd31eb653cafbaf8f3514e6e96690b013a3fd2410a5a70c28fece012593489f20'
    assert all(sha(PREVIOUS / 'source' / n) == h for n, h in m['source_sha256'].items())
    assert read(PREVIOUS / 'deployment-status.json')['phase'] == 'baseline_full_backup'
    assert read(BASE / 'infra/access-release.json')['release'] == m['previous_release']
    KIT.mkdir(); (KIT / 'private').mkdir(mode=0o700); (KIT / 'evidence').mkdir(); (KIT / 'tools').mkdir()
    shutil.copytree(PREVIOUS / 'source', KIT / 'source', ignore=shutil.ignore_patterns('__pycache__'))
    rendered = []
    for path in (KIT / 'source').rglob('*'):
        if path.is_file() and not path.is_relative_to(KIT / 'source/docs') and path.suffix in ('.py', '.sh', '.json', '.service', '.timer', '.path', '.conf'):
            text = path.read_text()
            if PRIOR in text:
                path.write_text(text.replace(PRIOR, NAME)); rendered.append(str(path.relative_to(KIT / 'source')))
    def replace(name, before, after):
        path = KIT / 'source' / name
        text = path.read_text()
        assert text.count(before) == 1, name
        path.write_text(text.replace(before, after))
    replace('infra/backend/router_backup.py', "'--checkers 1 --transfers 1',", "'--checkers 1 --transfers 1 --ftp-idle-timeout 10s',")
    replace('scripts/audit_release/backup_preflight.py', "    from image_cache import deduplicate, paths\n", '')
    replace('scripts/audit_release/backup_preflight.py', "        result = deduplicate(paths(core.BASE), manifest['offline_image_archive_sha256'], apply=True)",
            "        result = {'ok': True, 'applied': False, 'reason': 'new immutable image archive; historical cache files preserved'}")
    replace('scripts/audit_release/backup_preflight.py', "        print('Azonos, inaktív image-cache példányok ellenőrzése és helytakarékos összekapcsolása; mentési archívumot nem törlünk.', flush=True)",
            "        print('Új r22 mentési cache; a korábbi csomagok és archívumok megmaradnak.', flush=True)")
    replace('scripts/audit_release/backup_preflight.py', 'required = 2 * max(sizes or [3 * 1024 ** 3]) + 2 * 1024 ** 3',
            "required = 2 * max(sizes or [3 * 1024 ** 3]) + 2 * 1024 ** 3 + (core.KIT / 'private/access-images.tar.gz').stat().st_size")
    replace('scripts/audit_release/backup_preflight.py', '    return root\n',
            "    # The running r18 sources stay immutable; only this shadow worker receives\n    # the tested transport correction, alongside the existing logging overlay.\n    shutil.copyfile(core.KIT / 'source/infra/backend/router_backup.py', root / 'infra/backend/router_backup.py')\n    return root\n")
    replace('scripts/f10_release/deploy.py', "    link_archive(paths(BASE)[0],images/'access-images.tar.gz',m['offline_image_archive_sha256'],uid=os.geteuid())",
            "    shutil.copyfile(KIT/'private/access-images.tar.gz',images/'access-images.tar.gz')\n    if digest(images/'access-images.tar.gz') != m['offline_image_archive_sha256']:raise ValueError('Staged image archive changed')")
    # Runtime installation still uses the reviewed root-to-root hardlink from staging.
    path = KIT / 'source/scripts/audit_release/postcheck.py'
    path.write_text(path.read_text().replace('2026-11-02', '2026-11-03').replace('REPAIR-068', 'REPAIR-079'))
    for name in ('activate.py', 'backup_supervision.py'):
        path = KIT / 'source/scripts/audit_release' / name
        path.write_text(path.read_text().replace('r21', 'r22'))
    for rel in ('scripts/router_release/activate.py', 'scripts/router_release/prepare_audit_restore.py'):
        path = KIT / 'source' / rel
        path.write_text(path.read_text().replace('router-r21', 'router-r22').replace("say('r21:", "say('r22:")
                        .replace('hc-audit-final-r21-', 'hc-audit-final-r22-').replace('audit-final-r21-', 'audit-final-r22-'))
    for name in ('start_r22.py', 'test_start_r22.py', 'ftp_idle_pool_lab.py', 'test_transport_r22.py', 'summarize_r21_baseline_failure.py', 'test_summarize_r21_baseline_failure.py'):
        shutil.copyfile(BASE / 'scripts/audit_release' / name, KIT / 'source/scripts/audit_release' / name)
    for name in ('summarize_r21_baseline_failure.py', 'resume_r21.py'):
        origin = BASE / 'scripts/audit_release' / name if name.startswith('summarize') else BASE / 'backups/releases/hc-audit-20261102-r21-continuation-1/source/resume_r21.py'
        shutil.copyfile(origin, KIT / 'tools' / name)
    shutil.copyfile(PREVIOUS / 'tools/rclone', KIT / 'tools/rclone'); (KIT / 'tools/rclone').chmod(0o755)
    # Adapt the existing focused fixture to the explicit shadow transport overlay.
    path = KIT / 'source/scripts/audit_release/test_backup_preflight.py'
    text = path.read_text().replace("core.OLD_RUNTIME.mkdir();", "(core.KIT / 'source/infra/backend').mkdir(parents=True); (core.KIT / 'source/infra/backend/router_backup.py').write_text('reviewed transport overlay'); (core.OLD_RUNTIME / 'infra/backend').mkdir(parents=True); (core.KIT / 'private').mkdir(parents=True); (core.KIT / 'private/access-images.tar.gz').write_bytes(b'cache'); core.OLD_RUNTIME.mkdir(exist_ok=True);")
    text = text.replace("core = self.core(Path(d))\n            cache", "core = self.core(Path(d))\n            (core.KIT / 'private').mkdir(parents=True); (core.KIT / 'private/access-images.tar.gz').write_bytes(b'cache')\n            cache")
    text = text.replace("self.assertEqual((root / 'scripts/router_restic.py').read_text(), 'reviewed logging overlay')", "self.assertEqual((root / 'scripts/router_restic.py').read_text(), 'reviewed logging overlay')\n            self.assertEqual((root / 'infra/backend/router_backup.py').read_text(), 'reviewed transport overlay')\n            self.assertFalse((core.OLD_RUNTIME / 'infra/backend/router_backup.py').exists())")
    path.write_text(text)
    prior = copy.deepcopy(m)
    m.update(release=NAME, source_sha256={}, acceptance_sha256=None, ready_for_root_deploy=False,
             deployed=False, status='transport_fix_preparing_not_deployed', prior_attempt=PRIOR,
             retry_reason='reproduced expired FTP control connection; drain idle pool at 10s before 30s socket deadline')
    m['scope'] = [*m.get('scope', []), 'FTP idle-pool expiration before socket timeout']
    write(KIT / 'release.json', m)
    write(KIT / 'evidence/prior-r21-release.json', prior)
    shutil.copyfile(PREVIOUS / 'evidence/acceptance.json', KIT / 'evidence/prior-r21-acceptance.json')
    write(KIT / 'evidence/source-review.json', {'rendered_paths': rendered,
        'transport_change': '--ftp-idle-timeout 10s; existing timeout/retries/checkers/transfers/connections preserved',
        'baseline_overlay': 'r18 shadow only; current r18 release, archive recovery identity and live sources preserved',
        'new_archive': 'old cache archives preserved; budget includes a new root-owned staging cache',
        'application_logic_changes': 0, 'new_backend_transport_code': True, 'prior_r21_immutable': True})
    print(json.dumps({'release': NAME, 'prepared': True, 'deployed': False}))


def build():
    m = read(KIT / 'release.json'); root = KIT / 'build-inputs/backend'; root.mkdir(parents=True)
    shutil.copyfile(KIT / 'source/infra/backend/router_backup.py', root / 'router_backup.py')
    base = m['images']['backend']; tag = 'hc-audit-r22-base:20261103'
    subprocess.run(['docker', 'tag', base, tag], check=True)
    assert subprocess.check_output(['docker', 'image', 'inspect', tag, '-f', '{{.Id}}'], text=True).strip() == base
    (root / 'Dockerfile').write_text('FROM ' + tag + '\nCOPY router_backup.py /app/router_backup.py\nLABEL org.homecontrol.release="' + NAME + '"\n')
    with (KIT / 'evidence/build-backend.log').open('w') as log:
        subprocess.run(['docker', 'build', '--network=none', '--pull=false', '--no-cache', '-t', 'hc-audit-backend:20261103-r22', str(root)],
                       env={**os.environ, 'DOCKER_BUILDKIT': '0'}, stdout=log, stderr=subprocess.STDOUT, check=True)
    after = read_inspect('hc-audit-backend:20261103-r22'); before = read_inspect(base)
    for key in ('Env', 'Entrypoint', 'Cmd', 'User', 'Healthcheck', 'WorkingDir'):
        assert after['Config'].get(key) == before['Config'].get(key), key
    m['images']['backend'] = after['Id']
    model = read(KIT / 'source/runtime.compose.json'); model['services']['backend']['image'] = after['Id']
    write(KIT / 'source/runtime.compose.json', model)
    m['recovery_images'] = sorted({v['image'] for v in m['baseline'].values()} | set(m['images'].values()))
    write(KIT / 'release.json', m)
    write(KIT / 'evidence/candidate-image-lock.json', {'homecontrol-' + s.removeprefix('homecontrol-'): i for s, i in m['images'].items()})
    write(KIT / 'evidence/image-build.json', {'base_image': base, 'image': after['Id'], 'network': 'none', 'dependency_install_commands': 0,
          'runtime_contract_preserved': True, 'source_sha256': sha(root / 'router_backup.py')})
    print(json.dumps({'new_backend_image': after['Id'], 'reused_images': 2, 'deployed': False}))


def read_inspect(image): return json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]


def refresh():
    assert not read(KIT / 'release.json')['ready_for_root_deploy'], 'Never modify a sealed source'
    for name in ('ftp_idle_pool_lab.py', 'test_transport_r22.py'):
        shutil.copyfile(BASE / 'scripts/audit_release' / name, KIT / 'source/scripts/audit_release' / name)
    path = KIT / 'source/scripts/audit_release/postcheck.py'
    path.write_text(path.read_text().replace('r21', 'r22'))
    for rel in ('scripts/router_release/prepare_audit_restore.py',):
        path = KIT / 'source' / rel
        path.write_text(path.read_text().replace('r22-20261102', 'r22-20261103'))


def archive():
    m = read(KIT / 'release.json'); path = KIT / 'private/access-images.tar.gz'
    with path.open('xb') as raw:
        process = subprocess.Popen(['docker', 'image', 'save', *m['recovery_images']], stdout=subprocess.PIPE)
        with gzip.GzipFile(filename='', mode='wb', compresslevel=1, fileobj=raw, mtime=0) as zipped:
            shutil.copyfileobj(process.stdout, zipped, 1024 ** 2)
        process.stdout.close(); assert process.wait() == 0
        raw.flush(); os.fsync(raw.fileno())
    path.chmod(0o600)
    m.update(offline_image_archive_sha256=sha(path), rclone_sha256=sha(KIT / 'tools/rclone'))
    write(KIT / 'release.json', m)
    with (KIT / 'evidence/offline-load.log').open('w') as log:
        subprocess.run(['docker', 'image', 'load', '-i', str(path)], stdout=log, stderr=subprocess.STDOUT, check=True)
    for image in m['recovery_images']: assert read_inspect(image)['Id'] == image
    write(KIT / 'evidence/offline-load.json', {'ok': True, 'archive_sha256': sha(path), 'verified_images': m['recovery_images'], 'size_bytes': path.stat().st_size})
    print(json.dumps({'offline_load_verified': True, 'images': len(m['recovery_images']), 'size_bytes': path.stat().st_size}))


if __name__ == '__main__':
    {'source': source, 'build': build, 'archive': archive, 'refresh': refresh}[sys.argv[1]]()
