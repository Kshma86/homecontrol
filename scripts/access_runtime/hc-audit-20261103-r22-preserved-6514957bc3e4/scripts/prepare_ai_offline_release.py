#!/usr/bin/env python3
"""Prepare a separate, inactive AI-offline package. Never deploy or contact the AI host."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

BASE=Path(__file__).resolve().parents[1]
NAME='hc-refactor-ai-offline-20261027-r6'
PREVIOUS=BASE/'backups/releases/hc-refactor-20261026-r4'
RELEASE=BASE/'backups/releases'/NAME
OVERLAY=(
    'infra/backend/deployment_policy.py','infra/backend/app.py','infra/backend/ai_node_service.py',
    'infra/backend/combustion_safety_service.py','infra/backend/tests/test_combustion_opening_events.py',
    'infra/backend/ai_proxy_service.py','infra/backend/mqtt_monitor_service.py',
    'infra/backend/power_wall_service.py','infra/backend/process_binding_service.py',
    'infra/backend/backup_service.py','infra/backend/tests/test_deployment_policy.py',
    'scripts/backup_runner.py','scripts/install_backup_f6.py','scripts/deployment_policy_cli.py',
    'scripts/backup_weekly_worker.sh','scripts/backup_check_worker.sh',
    'scripts/backup_config_sync_worker.sh','scripts/backup_archive_worker.sh',
    'scripts/prepare_ai_offline_release.py','scripts/check_restricted_release.py',
    'scripts/prepare_release_secrets.py','scripts/rehearse_audit_release.py','scripts/rehearse_restricted_release.py',
    'scripts/preflight_restricted_release.py','docs/hc-ai-offline-release.md',
    'infra/frontend/src/main.jsx','infra/frontend/src/features/backup/Backup.jsx',
)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

def prepare_tuya(source, policy):
    target=source/'apps/tuya-poller/tuya_poller.py'
    text=(BASE/'apps/tuya-poller/tuya_poller.py').read_text()
    marker='    value = command_bool(payload.get("value", payload.get("state", payload.get("switch"))))'
    if text.count(marker)!=1:raise ValueError('Unexpected poller command implementation')
    text=text.replace('import json\n','import json\nimport deployment_policy\nif not deployment_policy.policy()["valid"]:\n    raise RuntimeError("Mandatory deployment policy invalid; startup refused")\n',1)
    guard='    if target is not None and deployment_policy.tuya_device_blocked(target.name, target.device_id):\n        publish_command_result(target.name, False, deployment_policy.MESSAGE, {"code": "deployment_restricted"})\n        return False\n'
    target.write_text(text.replace(marker,guard+marker))
    context=RELEASE/'tuya-build';context.mkdir(exist_ok=True)
    for name in ('deployment_policy.py','deployment_policy.json'):
        shutil.copy2(source/'infra/backend'/name,context/name)
    shutil.copy2(target,context/target.name)
    (context/'Dockerfile').write_text('FROM homecontrol-homecontrol-tuya-poller\nCOPY *.py /app/\nCOPY deployment_policy.json /app/deployment_policy.json\n')

def freeze():
    if RELEASE.exists():raise ValueError('Refusing to overwrite a prepared release')
    prior=json.loads((PREVIOUS/'release.json').read_text())
    for name,expected in prior['source_sha256'].items():
        if digest(PREVIOUS/'source'/name)!=expected:raise ValueError('Original r4 source integrity failed')
    RELEASE.mkdir(parents=True)
    source=RELEASE/'source';shutil.copytree(PREVIOUS/'source',source)
    (RELEASE/'evidence').mkdir()
    private=RELEASE/'private';private.mkdir(mode=0o700)
    runtime=private/'runtime/infra';runtime.mkdir(parents=True,mode=0o700)
    shutil.copy2(PREVIOUS/'private/runtime/infra/.env',runtime/'.env');(runtime/'.env').chmod(0o600)
    for name in OVERLAY:
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(BASE/name,target)
    module=source/'infra/backend/deployment_policy.py'
    module.write_text(module.read_text().replace('POLICY_REQUIRED = False','POLICY_REQUIRED = True'))
    policy=dict(version=1,profile='ai-offline',blocked_entity_ids=[121],
                blocked_command_topics=['homecontrol/cmd/tuya/Mosógép/switch'],
                blocked_tuya_device_ids=['bf1d8186d331470cafxzfz'])
    write_json(module.with_suffix('.json'),policy)
    prepare_tuya(source,policy)
    for name,mode in (('backup_hc.sh','local'),('weekly_ai_backup.sh','weekly'),
                      ('sync_config_to_gitea.sh','git'),('restic_check_ai_backup.sh','check')):
        target=source/'scripts'/name
        target.write_text('#!/usr/bin/env bash\nset -Eeuo pipefail\nBASE="/srv/docker/homecontrol"\nexec /usr/bin/python3 "$BASE/scripts/backup_runner.py" --mode '+mode+'\n')
        target.chmod(0o755)
    for name in ('gitea_config_status_f1.sh','gitea_config_restore.sh'):
        target=source/'scripts'/name
        text=target.read_text();first,rest=text.split('\n',1)
        guard='python3 "$(dirname -- "${BASH_SOURCE[0]}")/deployment_policy_cli.py" --worker-mode git || exit $?\n'
        target.write_text(first+'\n'+guard+rest)
    builds=RELEASE/'builds';builds.mkdir()
    (builds/'backend.Dockerfile').write_text('FROM homecontrol-backend:hc-refactor-20261026-r4\nCOPY *.py /app/\nCOPY deployment_policy.json /app/deployment_policy.json\nCOPY static /app/static\n')
    shutil.copy2(PREVIOUS/'builds/frontend.Dockerfile',builds/'frontend.Dockerfile')
    rollback=RELEASE/'rollback-build';rollback.mkdir()
    for name in ('deployment_policy.py','deployment_policy.json','ai_node_service.py','ai_proxy_service.py','combustion_safety_service.py',
                 'ai_power_coordination.py','backup_protocol.py','mqtt_monitor_service.py'):
        shutil.copy2(source/'infra/backend'/name,rollback/name)
    adapter=(PREVIOUS/'rollback-build/refactor_rollback_wsgi.py').read_text()
    adapter=adapter.replace('app=hc.app','app=hc.app\nfrom deployment_policy import install_routes\ninstall_routes(app)')
    (rollback/'refactor_rollback_wsgi.py').write_text(adapter)
    (rollback/'Dockerfile').write_text('FROM homecontrol-backend:hc-refactor-20261026-r4-rollback\nCOPY *.py /app/\nCOPY deployment_policy.json /app/deployment_policy.json\n')
    images={'backend':'homecontrol-backend:'+NAME,'frontend':'homecontrol-frontend:'+NAME,
            'tuya':'homecontrol-tuya-poller:'+NAME,
            'ingest':'homecontrol-ingest:hc-refactor-20261026-r4'}
    fallback='homecontrol-backend:'+NAME+'-rollback'
    disabled_env={'AI_NODE_HOST':'','AI_NODE_MAC':'','AI_SERVER_URL':'http://127.0.0.1:9'}
    for mode in ('release','rollback'):
        write_json(RELEASE/(mode+'.override.json'),{'services':{
            'backend':{'image':images['backend'] if mode=='release' else fallback,'environment':disabled_env},
            'frontend':{'image':images['frontend'] if mode=='release' else prior['previous_frontend']},
            'hc_ingest':{'image':images['ingest'] if mode=='release' else prior['previous_ingest']},
            'homecontrol-tuya-poller':{'image':images['tuya']}}})
    command=json.loads((PREVIOUS/'compose-command.json').read_text())
    command=[str(x).replace(str(PREVIOUS),str(RELEASE)) for x in command]
    write_json(RELEASE/'compose-command.json',command)
    manifest={k:v for k,v in prior.items() if k not in ('source_sha256','package_sha256','image_ids','private_env_sha256','encrypted_bundle_sha256')}
    manifest.update(release=NAME,state='preparing_not_deployed',images=images,rollback_image=fallback,
                    profile='ai-offline',preparation_complete=False,production_changed=False,physical_commands=False,
                    remaining_checks=['HC-45: real empty-VM systemd full restore/repeat/rollback remains unverified',
                                      'Fresh local pre-cutover backup and explicit coordinated host/container handover'],
                    deferred_checks=['HC-31: physical AI shutdown/wake after SSD repair; AI functions disabled in this profile'])
    manifest['previous_backend']='homecontrol-backend:hc-opening-events-20261027-r4'
    manifest['preserved_live_release']='hc-opening-events-20261027-r4'
    manifest['preserved_live_sources']={'combustion_safety_service.py':digest(source/'infra/backend/combustion_safety_service.py')}
    active=json.loads((BASE/'backups/releases/hc-opening-events-20261027-r4/release.json').read_text())
    if manifest['preserved_live_sources']['combustion_safety_service.py']!=active['source_sha256']:
        raise ValueError('Prepared safety source differs from the already deployed baseline')
    write_json(RELEASE/'release.json',manifest)
    return {'release':NAME,'state':manifest['state'],'production_changed':False}

def seal():
    source=RELEASE/'source';manifest=json.loads((RELEASE/'release.json').read_text())
    if manifest.get('preparation_complete'):raise ValueError('Release is already sealed')
    ciphertext=RELEASE/'private/homecontrol-secrets-prepared.tar.gz.age'
    shutil.copy2(ciphertext,source/'secrets/homecontrol-secrets-latest.tar.gz.age')
    bundle=source/'secrets/homecontrol-secrets-latest.tar.gz.age'
    (bundle.with_name(bundle.name+'.sha256')).write_text(digest(bundle)+'  '+bundle.name+'\n')
    exports=json.loads((source/'EXPORT_MANIFEST.json').read_text())
    exports['files']=[{'path':p.relative_to(source).as_posix(),'sha256':digest(p)}
                      for p in sorted(source.rglob('*')) if p.is_file() and p.name!='EXPORT_MANIFEST.json']
    write_json(source/'EXPORT_MANIFEST.json',exports)
    manifest['source_sha256']={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*')) if p.is_file()}
    manifest['private_env_sha256']=digest(RELEASE/'private/runtime/infra/.env')
    manifest['encrypted_bundle_sha256']=digest(ciphertext)
    import subprocess
    names=set(manifest['images'].values())|{manifest['rollback_image'],manifest['previous_backend'],manifest['previous_frontend'],manifest['previous_ingest']}
    manifest['image_ids']={name:json.loads(subprocess.check_output(['docker','image','inspect',name]))[0]['Id'] for name in sorted(names)}
    manifest['package_sha256']={p.relative_to(RELEASE).as_posix():digest(p) for p in sorted(RELEASE.rglob('*'))
        if p.is_file() and p.relative_to(RELEASE).parts[0] not in ('source','private','evidence') and p.name!='release.json'}
    manifest.update(state='prepared_not_deployed',preparation_complete=True)
    write_json(RELEASE/'release.json',manifest)
    return {'release':NAME,'state':manifest['state'],'preparation_complete':True,'production_changed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--freeze',action='store_true');group.add_argument('--seal',action='store_true')
    args=parser.parse_args()
    print(json.dumps(freeze() if args.freeze else seal() if args.seal else
                     {'action':'plan','release':NAME,'production_changed':False},indent=2))
