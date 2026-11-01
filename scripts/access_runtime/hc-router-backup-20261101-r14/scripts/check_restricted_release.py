#!/usr/bin/env python3
"""Read-only check of the separate sealed AI-offline candidate. Never deploys."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE=Path(__file__).resolve().parents[1]
RELEASE=BASE/'backups/releases/hc-refactor-ai-offline-20261027-r6'

def check(root=RELEASE):
    root=Path(root);manifest=json.loads((root/'release.json').read_text())
    if (root/'SUPERSEDED.json').exists():raise ValueError('Release was superseded; do not deploy')
    if not manifest.get('preparation_complete'):raise ValueError('Release is not sealed')
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    for name,expected in manifest['source_sha256'].items():
        if digest(root/'source'/name)!=expected:raise ValueError('Frozen source changed: '+name)
    for name,expected in manifest['package_sha256'].items():
        if digest(root/name)!=expected:raise ValueError('Package artifact changed: '+name)
    for name,key in (('private/runtime/infra/.env','private_env_sha256'),
                     ('private/homecontrol-secrets-prepared.tar.gz.age','encrypted_bundle_sha256')):
        if digest(root/name)!=manifest[key]:raise ValueError('Private artifact changed; values withheld')
    module=root/'source/infra/backend/deployment_policy.py'
    for name,expected in manifest.get('preserved_live_sources',{}).items():
        if digest(root/'source/infra/backend'/name)!=expected or digest(root/'rollback-build'/name)!=expected:
            raise ValueError('Previously deployed safety fix missing: '+name)
    if 'POLICY_REQUIRED = True' not in module.read_text():raise ValueError('Mandatory policy missing')
    policy=json.loads(module.with_suffix('.json').read_text())
    if policy['profile']!='ai-offline' or policy['blocked_entity_ids']!=[121]:raise ValueError('Wrong restricted identity')
    if 'homecontrol/cmd/tuya/Mosógép/switch' not in policy['blocked_command_topics']:raise ValueError('AI topic guard missing')
    if policy.get('blocked_tuya_device_ids')!=['bf1d8186d331470cafxzfz']:raise ValueError('Physical Tuya identity guard missing')
    for name,expected in manifest['image_ids'].items():
        row=json.loads(subprocess.check_output(['docker','image','inspect',name]))[0]
        if row['Id']!=expected:raise ValueError('Pinned image changed: '+name)
    command=json.loads((root/'compose-command.json').read_text())
    for mode in ('release','rollback'):
        result=subprocess.run(command+['-f',str(root/(mode+'.override.json')),'config','--format','json'],capture_output=True,text=True)
        if result.returncode:raise ValueError('Compose render failed; private values withheld')
        services=json.loads(result.stdout)['services'];env=services['backend']['environment']
        if env.get('AI_NODE_HOST') or env.get('AI_NODE_MAC'):raise ValueError('AI connection still configured')
        if env.get('AI_SERVER_URL')!='http://127.0.0.1:9':raise ValueError('AI gateway connection still configured')
        if not env['DATABASE_URL'].startswith('postgresql://hc_app:'):raise ValueError('Incorrect runtime role')
        if not env['SQL_LAB_DATABASE_URL'].startswith('postgresql://hc_lab:'):raise ValueError('Incorrect reader role')
        if services['hc_ingest']['environment']['PG_USER']!='hc_app':raise ValueError('Incorrect ingest role')
        if services['homecontrol-tuya-poller']['image']!=manifest['images']['tuya']:raise ValueError('Restricted Tuya consumer missing')
    return dict(integrity_ok=True,compose_ok=True,profile='ai-offline',preparation_complete=True,
                production_changed=False,ready_for_unconditional_deploy=False,
                remaining_checks=manifest['remaining_checks'],deferred_checks=manifest['deferred_checks'])

if __name__=='__main__':print(json.dumps(check(),indent=2))
