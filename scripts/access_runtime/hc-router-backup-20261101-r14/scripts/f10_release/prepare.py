"""Freeze an application-only r11 release on the installed r10 access platform."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

BASE=Path(__file__).resolve().parents[2]
OLD='hc-access-20261030-r10'
NAME='hc-router-backup-20261101-r14'
KIT=BASE/'backups/releases'/NAME
RUNTIME=BASE/'scripts/access_runtime'/NAME
PRIVATE=BASE/'infra/ssh'/NAME
MAPPING={'backend':'backend','ingest':'hc_ingest','tuya-poller':'homecontrol-tuya-poller',
 'gree-climate':'homecontrol-gree-climate','xiaomi-x10':'homecontrol-xiaomi-x10',
 'ha-growatt-poller':'homecontrol-ha-growatt-poller','ai-server':'ai-server','frontend':'frontend'}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    if KIT.exists():raise ValueError('Do not overwrite an existing release')
    candidate=BASE/'backups/releases/hc-f10-20261031-candidate'
    info=json.loads((candidate/'manifest.json').read_text())
    assert info['status']=='verified_local_partial_audit_not_deployed'
    model=json.loads((BASE/'infra/docker-compose.yml').read_text())
    source=KIT/'source'
    shutil.copytree(BASE/'scripts/access_runtime'/OLD,source,ignore=shutil.ignore_patterns('__pycache__'))
    # Only platform paths are rendered. SQL files, original audit and firmware
    # references retain their existing checksums. The firewall table stays hc41_r10.
    for path in source.rglob('*'):
        if path.is_file() and (path.suffix in ('.py','.sh','.service','.timer','.path','.conf')
                              or path.name=='canonical_backup_runner.py'):
            text=path.read_text()
            if OLD in text:path.write_text(text.replace(OLD,NAME))
    worker=source/'scripts/backup_archive_worker.sh'
    worker.write_text(worker.read_text().replace("ssh/"+NAME+"/images", "ssh/*/images"))
    for component,item in info['components'].items():
        dest=source/item['folder'];dest.mkdir(parents=True,exist_ok=True)
        for path in (candidate/component/'source').glob('*.py'):
            shutil.copyfile(path,dest/path.name)
        for name in ('requirements.lock','requirements.security.lock','requirements.txt','Dockerfile'):
            path=BASE/item['folder']/name
            if path.exists():shutil.copyfile(path,dest/name)
    for name in ('package.json','package-lock.json','Dockerfile'):
        shutil.copyfile(BASE/'infra/frontend'/name,source/'infra/frontend'/name)
    for component,service in MAPPING.items():
        model['services'][service]['image']=info['verified_images'][component]
        model['services'][service].pop('build',None)
        model['services'][service]['pull_policy']='never'
        for entry in model['services'][service].get('env_file',[]):
            entry['path']=entry['path'].replace('/'+OLD+'/', '/'+NAME+'/')
        for entry in model['services'][service].get('volumes',[]):
            entry['source']=entry['source'].replace('/'+OLD+'/', '/'+NAME+'/')
    (source/'runtime.compose.json').write_text(json.dumps(model,indent=2)+'\n')
    (source/'binding-release.json').write_text(json.dumps({'findings':['HC-35','HC-36'],
        'backend_image':info['verified_images']['backend'],'frontend_image':info['verified_images']['frontend']},indent=2)+'\n')
    (source/'scripts/f10_release').mkdir(exist_ok=True)
    for path in (BASE/'scripts/f10_release').glob('*.py'):
        shutil.copyfile(path,source/'scripts/f10_release'/path.name)
    private=KIT/'private';private.mkdir(mode=0o700)
    # No production environment or password is read here. Root deployment copies
    # the already approved r10 identities and creates the new encrypted bundle.
    raw=json.loads(subprocess.check_output(['docker','inspect',*subprocess.check_output(
        ['docker','ps','-aq'],text=True).split()],text=True))
    baseline={x['Name'].lstrip('/'):{'id':x['Id'],'image':x['Image']} for x in raw}
    manifest={'release':NAME,'previous_release':OLD,'prepared':True,'deployed':False,
      'changed_services':list(MAPPING.values()),'components':MAPPING,
      'images':{service:info['verified_images'][component] for component,service in MAPPING.items()},
      'baseline':baseline,'previous_compose_sha256':sha(BASE/'infra/docker-compose.yml'),
      'source_sha256':{str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file()},
      'scope':['HC-12','HC-32','HC-23 partial','HC-43 partial'],
      'unchanged':['postgres','pgbouncer','mqtt','zigbee2mqtt','proxy','mdns','homeassistant'],
      'pending_root_steps':['private clone and encrypted bundle roundtrip','fresh verified backup','cutover and supervised acceptance'],
      'ready_for_root_deploy':False}
    (KIT/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (KIT/'evidence').mkdir()
    print(json.dumps({'release':NAME,'changed_services':len(MAPPING),'production_changed':False}))


if __name__=='__main__':prepare()
