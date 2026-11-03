"""Prepare capacity, then prove a full current-platform backup before cutover."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import sys


def prepare(core, manifest):
    from backup_supervision import install
    if os.geteuid() != 0:
        raise PermissionError('Real local root is required')
    with ExitStack() as stack:
        core.locked(stack)
        core.idle()
        print('Új r22 mentési cache; a korábbi csomagok és archívumok megmaradnak.', flush=True)
        result = {'ok': True, 'applied': False, 'reason': 'new immutable image archive; historical cache files preserved'}
        core.platform().write_json(core.KIT / 'evidence/image-cache-capacity.json', result, 0o644)
    sizes = []
    for path in (core.BASE / 'backups').glob('homecontrol_*.tar.gz.complete.json'):
        receipt = json.loads(path.read_text())
        if receipt.get('completed') is True:
            sizes.append(receipt['size_bytes'])
    required = 2 * max(sizes or [3 * 1024 ** 3]) + 2 * 1024 ** 3 + (core.KIT / 'private/access-images.tar.gz').stat().st_size
    if shutil.disk_usage(core.BASE).free < required:
        raise ValueError('Insufficient space for pre/post backups plus 2 GiB reserve')
    install(core)
    core.fresh_backup = lambda: prove_current_backup(core, manifest)


def baseline_runner(core):
    root = core.KIT / 'private/baseline-runner'
    if root.exists():
        raise ValueError('Baseline runner already exists; inspect previous attempt')
    prior = json.loads((core.BASE / 'backups/releases' / core.OLD / 'release.json').read_text())
    for name, expected in prior['source_sha256'].items():
        if core.digest(core.OLD_RUNTIME / name) != expected:
            raise ValueError('Previous runtime changed before baseline backup')
    shutil.copytree(core.OLD_RUNTIME, root, ignore=shutil.ignore_patterns('__pycache__'))
    # Preserve NAME/PRIVATE=r18 in this shadow executor. Its archive contains
    # the actual current r18 recovery cache, not a candidate cache under r18 metadata.
    for name in ('router_restic.py', 'router_operation_log.py'):
        shutil.copyfile(core.KIT / 'source/scripts' / name, root / 'scripts' / name)
    # The running r18 sources stay immutable; only this shadow worker receives
    # the tested transport correction, alongside the existing logging overlay.
    shutil.copyfile(core.KIT / 'source/infra/backend/router_backup.py', root / 'infra/backend/router_backup.py')
    return root


def prove_current_backup(core, manifest):
    from backup_supervision import supervised_call
    root = baseline_runner(core)
    state_path = core.BASE / 'backups/backup-state.json'
    previous = json.loads(state_path.read_text()).get('run_id')
    print('Teljes r18 HC/Git/router előmentés indul a szolgáltatások leállítása előtt.', flush=True)
    core.phase('baseline_full_backup')
    supervised_call(core.call, [sys.executable, str(root / 'scripts/hostops/backup_runner.py'), '--mode', 'weekly'])
    state = json.loads(state_path.read_text())
    if (state.get('run_id') == previous or state.get('state') != 'completed'
            or state.get('mode') != 'weekly' or state.get('scope') != 'router'):
        raise ValueError('No new completed baseline weekly backup')
    for name in ('local_archive', 'restic', 'git_offsite', 'secrets_bundle'):
        if state.get('targets', {}).get(name, {}).get('state') != 'succeeded':
            raise ValueError('Baseline backup target incomplete: ' + name)
    with ExitStack() as stack:
        core.locked(stack)
        sys.path.insert(0, str(core.KIT / 'source/infra/backend'))
        from backup_protocol import verify_archive
        receipt = state['archive']
        archive = core.BASE / 'backups' / receipt['name']
        core.platform().no_symlinks(archive)
        checked = verify_archive(archive)
        if receipt.get('completed') is not True or checked['sha256'] != receipt['sha256']:
            raise ValueError('Baseline local archive no longer matches receipt')
        print('R18 előmentés visszaolvasása és izolált PostgreSQL-restore; a szolgáltatások tovább futnak.', flush=True)
        core.phase('baseline_restore_proof')
        core.call([sys.executable, str(root / 'scripts/restore_smoke.py'), '--db-check'], timeout=7200,
                  extra_env={'HC_RESTORE_POSTGRES_IMAGE': manifest['baseline']['homecontrol-postgres']['image']})
        smoke = json.loads((core.BASE / 'backups/restore-smoke-result.json').read_text())
        if not (smoke.get('ok') and smoke.get('restic') == 'sha256_verified'
                and smoke.get('database') == 'restore_verified_without_owner_acl'
                and smoke.get('restic_archive', {}).get('sha256') == receipt['sha256']):
            raise ValueError('Baseline router/PG restore proof failed')
        proof = {'ok': True, 'release': core.OLD, 'run_id': state['run_id'],
                 'snapshot_id': smoke['snapshot_id'], 'archive_sha256': receipt['sha256'],
                 'git': 'pushed', 'restore': 'verified', 'database': 'verified',
                 'platform_still_running': True}
        core.platform().write_json(core.KIT / 'evidence/baseline-backup-restore.json', proof, 0o644)
        core.platform().write_json(core.KIT / 'private/pre-backup.json', {'name': archive.name, **checked})
