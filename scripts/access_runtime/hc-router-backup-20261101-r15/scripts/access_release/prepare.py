#!/usr/bin/env python3
"""Freeze/build the access release; never switch production containers or units."""
import argparse
import copy
import json
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from common import BASE, NAME, PRIVATE, RUNTIME, SERVICES, digest, units, write_json

BACKEND_FILES=('app.py','api_route_modules.py','system_status_service.py','mqtt_monitor_service.py',
    'host_operations_client.py','scoped_ai_power_coordination.py','mqtt_credentials.py','mqtt_read_probe.py',
    'restore_runtime_schema.py','migrate_hc07.py','migrate_hc38.py','migrate_hc39.py',
    'baseline_contract.py','db_privilege_manifest.py','sql_lab_database.py',
    'process_binding_service.py','climate_fan_coordination.py','power_wall_service.py',
    'ai_node_service.py','climate_service.py','energy_device_service.py','irrigation_service.py')
FRONTEND_FILES=('src/features/admin/HcAdmin.jsx','src/entityHelpers.js','tests/process-bindings.test.mjs')
APPS={'hc_ingest':('hc_ingest',('mqtt_ingest_multi.py','mqtt_credentials.py')),
    'homecontrol-tuya-poller':('tuya-poller',('tuya_poller.py','mqtt_credentials.py')),
    'homecontrol-xiaomi-x10':('xiaomi-x10',('xiaomi_x10_bridge.py','xiaomi_x10_api.py','mqtt_credentials.py')),
    'homecontrol-gree-climate':('gree-climate',('gree_climate_bridge.py','mqtt_credentials.py')),
    'homecontrol-ha-growatt-poller':('ha-growatt-poller',('ha_growatt_poller.py','mqtt_credentials.py'))}


def render_bootstrap(text):
    helper='"$PROJECT_DIR/scripts/access_release/restore_assets.py"'
    text=text.replace('    openssh-client \\\n','    openssh-client \\\n    nftables \\\n')
    text=text.replace('up -d --build','up -d --no-build --pull never')
    old='    docker run --rm --network none -i postgres:16 pg_restore --list'
    assert old in text
    text=text.replace(old,
        '    RESTORE_ASSETS="$(python3 '+helper+' stage --archive "$SELECTED_ARCHIVE" --work "$WORK_ROOT")"\n'
        '    PG_RESTORE_IMAGE="$(python3 '+helper+' load --manifest "$RESTORE_ASSETS")"\n'
        '    docker run --rm --pull never --network none -i "$PG_RESTORE_IMAGE" pg_restore --list')
    text=text.replace('    stop_existing_stacks_for_apply\n',
        '    stop_existing_stacks_for_apply\n'
        '    if [ -n "${RESTORE_ASSETS:-}" ]; then\n'
        '      python3 '+helper+' quiesce --manifest "$RESTORE_ASSETS"\n    fi\n')
    text=text.replace('    apply_secrets\n',
        '    apply_secrets\n'
        '    if [ -n "${RESTORE_ASSETS:-}" ]; then\n'
        '      python3 '+helper+' apply --manifest "$RESTORE_ASSETS"\n    fi\n')
    text=text.replace('  if [ "$RESTORE_DB" = "true" ]; then\n    restore_database',
        '  if [ "$APPLY" = true ] && [ "$START_STACK" = true ]; then\n    python3 "'+str(RUNTIME)+'/scripts/access_release/install.py" restore-prepare\n  fi\n  if [ "$RESTORE_DB" = "true" ]; then\n    restore_database')
    text=text.replace('  start_stacks\n','  if [ "$START_STACK" = true ]; then\n    python3 "'+str(RUNTIME)+'/scripts/access_release/install.py" start-runtime\n  fi\n  start_stacks\n')
    return text


def render_f6_installer(text):
    # systemctl stop returns 5 for a unit absent on an empty host. Treat it as
    # already stopped only in the explicitly selected fresh-host installation.
    text=text.replace("call(['systemctl','stop','homecontrol-backup-apply.path'])", "call(['systemctl','stop','homecontrol-backup-apply.path'],allowed=(0,5) if fresh_host else (0,))")
    text=text.replace("for name in enabled: call(['systemctl','stop',name])", "for name in enabled: call(['systemctl','stop',name],allowed=(0,5) if fresh_host else (0,))")
    text=text.replace('import subprocess\n','import subprocess\nimport time\n')
    original='''                        value=call(['systemctl','show',name,'--property=NextElapseUSecRealtime,NextElapseUSecMonotonic','--no-pager']).stdout.strip()
                        if not any(line.partition('=')[2].strip() not in ('','0','infinity','n/a') for line in value.splitlines()):
                            raise RuntimeError('Restored timer has no next trigger: '+name)'''
    replacement='''                        deadline=time.monotonic()+60
                        while True:
                            value=call(['systemctl','show',name,'--property=NextElapseUSecRealtime,NextElapseUSecMonotonic','--no-pager']).stdout.strip()
                            if any(line.partition('=')[2].strip() not in ('','0','infinity','n/a') for line in value.splitlines()):break
                            if time.monotonic()>=deadline:raise RuntimeError('Restored timer has no next trigger: '+name)
                            time.sleep(.5)'''
    assert original in text
    text=text.replace(original,replacement)
    return text


def run(args, **kwargs):
    result=subprocess.run(args,capture_output=True,**kwargs)
    if result.returncode:raise RuntimeError('Preparation command failed: '+str(args[0]))
    return result.stdout


def active():
    names=run(['docker','ps','-a','--format','{{.Names}}'],text=True).splitlines()
    records=json.loads(run(['docker','inspect',*[n for n in names if n.startswith('homecontrol-') or n=='zigbee2mqtt']],text=True))
    rows={r['Config']['Labels'].get('com.docker.compose.service'):r for r in records if r['Config'].get('Labels',{}).get('com.docker.compose.project')=='homecontrol'}
    labels=rows['hc_ingest']['Config']['Labels']
    command=['docker','compose','--profile','ha-growatt','--project-directory',str(BASE/'infra'),
        '--env-file',labels['com.docker.compose.project.environment_file']]
    for file in labels['com.docker.compose.project.config_files'].split(','):command+=['-f',file]
    return rows,json.loads(run(command+['config','--format','json'],text=True)),command


def pin_network_addresses(model, rows, network):
    """Preserve every HC endpoint so Docker boot allocation cannot steal broker IP."""
    subnet=ipaddress.IPv4Network(network['IPAM']['Config'][0]['Subnet'])
    endpoints={}
    for service,row in rows.items():
        if service not in model['services']:continue
        attachment=row['NetworkSettings']['Networks'].get(network['Name'])
        if attachment is None:continue
        address=ipaddress.IPv4Address(attachment['IPAddress'])
        if address not in subnet or str(address) in endpoints.values():
            raise ValueError('Invalid or duplicate HC network address')
        endpoints[row['Name'].lstrip('/')]=str(address)
        model['services'][service]['networks']={'default':{'ipv4_address':str(address)}}
    actual={r['Name']:r['IPv4Address'].split('/')[0] for r in network['Containers'].values()}
    if actual!=endpoints:raise ValueError('Shared or changed Docker network; reconcile all endpoints first')
    return endpoints


def freeze(destination):
    destination=Path(destination).resolve();destination.mkdir(mode=0o755)
    private=destination/'private';private.mkdir(mode=0o700)
    source=destination/'source';source.mkdir()
    rows,model,command=active()
    # Preserve private rollback render, not only a mutable symlink.
    rollback=copy.deepcopy(model)
    for service,row in rows.items():
        if service not in rollback['services']:continue
        definition=rollback['services'][service]
        definition.update(environment=dict(item.split('=',1) for item in row['Config']['Env']),image=row['Image'])
        definition.pop('build',None);definition.pop('env_file',None)
    rollback['services']['mqtt']['networks']={'default':{'ipv4_address':next(iter(rows['mqtt']['NetworkSettings']['Networks'].values()))['IPAddress']}}
    write_json(private/'rollback.compose.json',rollback)
    write_json(private/'previous-command.json',command)
    previous=BASE/'backups/releases/hc-read-models-20261028-r8/source/infra/backend'
    shutil.copytree(previous,source/'infra/backend')
    shutil.copytree(previous.parents[1]/'docs',source/'docs')
    shutil.copytree(BASE/'infra/db',source/'infra/db')
    shutil.copytree(previous.parents[1]/'apps/ai-server',source/'apps/ai-server')
    shutil.copytree(BASE/'scripts',source/'scripts',ignore=shutil.ignore_patterns('__pycache__','access_runtime'))
    for name in BACKEND_FILES:shutil.copyfile(BASE/'infra/backend'/name,source/'infra/backend'/name)
    shutil.copytree(previous.parent/'frontend',source/'infra/frontend',ignore=shutil.ignore_patterns('node_modules','dist'))
    for name in FRONTEND_FILES:shutil.copyfile(BASE/'infra/frontend'/name,source/'infra/frontend'/name)
    # HC-35/36 and HC-41/44 ship together, retaining the r8 dependency baseline.
    for folder,names in APPS.values():
        target=source/'apps'/folder;target.mkdir(parents=True)
        for name in names:shutil.copyfile(BASE/'apps'/folder/name,target/name)
        for name in ('Dockerfile','requirements.txt'):
            if (BASE/'apps'/folder/name).exists():shutil.copyfile(BASE/'apps'/folder/name,target/name)
    for name in ('test_host_operations.py','test_mqtt_credentials.py','test_access_release.py','test_backup_runner.py','test_backup_units.py','test_deployment_policy.py',
                 'test_process_binding_service.py','test_process_binding_postgres.py','test_power_wall_service.py'):
        shutil.copyfile(BASE/'infra/backend/tests'/name,source/'infra/backend/tests'/name)
    shutil.copyfile(BASE/'infra/backend/tests/test_read_runtime_repair.py',source/'infra/backend/tests/test_read_runtime_repair.py')
    # Snapshot this turn's installer into the frozen source, including exact F6 code.
    draft=BASE/'backups/mqtt-access/hc41-20261030-explorer'
    secrets=private/'runtime';secrets.mkdir()
    mqtt=secrets/'mqtt';shutil.copytree(draft,mqtt)
    broker=mqtt/'broker';broker.mkdir()
    for name in ('authenticated.acl','legacy.acl'):shutil.copyfile(mqtt/name,broker/name)
    (broker/'mosquitto.conf').write_text((mqtt/'mosquitto.conf').read_text().replace('/credentials/passwords','/passwords'))
    shutil.copyfile(mqtt/'credentials/passwords',broker/'passwords')
    overrides=json.loads((mqtt/'compose.override.json').read_text())['services']
    runtime_env=secrets/'compose-env';runtime_env.mkdir(mode=0o700)
    network_name=next(iter(rows['mqtt']['NetworkSettings']['Networks']))
    network=json.loads(run(['docker','network','inspect',network_name],text=True))[0]
    if network['EnableIPv6']:raise ValueError('This reviewed network plan requires IPv4-only Docker bridge')
    subnet=network['IPAM']['Config'][0]['Subnet'];gateway=network['IPAM']['Config'][0]['Gateway']
    broker_ip=rows['mqtt']['NetworkSettings']['Networks'][network_name]['IPAddress']
    endpoints=pin_network_addresses(model,rows,network)
    pin_network_addresses(rollback,rows,network)
    write_json(private/'rollback.compose.json',rollback)
    for service,definition in model['services'].items():
        definition.pop('build',None);definition['pull_policy']='never'
        if service in rows:definition['image']=rows[service]['Image']
        env=definition.pop('environment',{}) or {}
        if service in rows:
            # Preserve the actual running environment, including service-specific
            # frozen releases, rather than re-interpolating an older .env file.
            env=dict(item.split('=',1) for item in rows[service]['Config']['Env'])
        if service in overrides:
            env.update(overrides[service].get('environment',{}))
        if service=='zigbee2mqtt':
            env.update(ZIGBEE2MQTT_CONFIG_MQTT_SERVER='mqtt://mqtt:1884',ZIGBEE2MQTT_CONFIG_MQTT_USER='hc_zigbee2mqtt',
                ZIGBEE2MQTT_CONFIG_MQTT_PASSWORD=(mqtt/'credentials/zigbee2mqtt.password').read_text().strip())
        if env:
            if any('\n' in str(v) or '\r' in str(v) for v in env.values()):raise ValueError('Multiline container environment requires explicit review')
            file=runtime_env/(service+'.env');file.write_text(''.join(k+'='+str(v or '')+'\n' for k,v in env.items()));file.chmod(0o600)
            definition['env_file']=[dict(path=str(PRIVATE/'compose-env'/file.name),format='raw')]
        else:definition.pop('env_file',None)
        if service in APPS or service=='backend':
            # New password mount targets only this service's secret, never a directory.
            role=overrides[service]['environment']['MQTT_USERNAME'][3:]
            definition.setdefault('volumes',[]).append(dict(type='bind',source=str(PRIVATE/'mqtt/credentials'/(role+'.password')),target='/run/secrets/hc-mqtt.password',read_only=True))
        if service=='backend':
            before=definition['volumes'][-1:]
            definitions=[]
            for mount in rows['backend']['Mounts']:
                if mount['Destination']=='/var/run/docker.sock':continue
                definitions.append(dict(type='bind',source=mount['Source'],target=mount['Destination'],read_only=True))
            for relative in ('backups/ai-control','backups/homecontrol-backup.lock','backups/ai-backup.lock','infra/private'):
                definitions.append(dict(type='bind',source=str(BASE/relative),target=str(BASE/relative)))
            definitions.append(dict(type='bind',source='/run/homecontrol-hostops',target='/run/hc-host-ops',read_only=True))
            definition.update(user='10001:10001',read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],tmpfs=['/tmp:rw,exec,nosuid,nodev,size=128m'],volumes=definitions+before)
            with (runtime_env/(service+'.env')).open('a') as f:f.write('HC_HOST_OPS_SOCKET=/run/hc-host-ops/operations.sock\nHOME=/tmp\n')
        if service=='mqtt':
            definition['volumes']=[m for m in definition['volumes'] if m['target']!='/mosquitto/config']
            definition['volumes'].append(dict(type='bind',source=str(PRIVATE/'mqtt/broker'),target='/mosquitto/config',read_only=True))
            definition['ports'].append(dict(target=1884,published='1884',host_ip='127.0.0.1',protocol='tcp'))
            definition['networks']={'default':{'ipv4_address':broker_ip}}
    model['networks']={'default':{'external':True,'name':network_name}}
    policy=dict(esp_ip='192.168.1.179',broker_ip=broker_ip,docker_subnet=subnet,dashboard_ip='192.168.1.89',mode='authenticated',owned_chain=False,esp_confirmed=False)
    write_json(secrets/'network-policy.json',policy)
    (source/'runtime.compose.json').write_text(json.dumps(model,indent=2)+'\n')
    # A canonical runner launcher is installed later, never into the working tree now.
    (source/'canonical_backup_runner.py').write_text((BASE/'scripts/hostops/canonical_backup_runner.py.in').read_text().replace('@RELEASE_ROOT_JSON@',json.dumps(str(RUNTIME))))
    bootstrap=source/'scripts/bootstrap_restore_v0_1.sh';bootstrap.write_text(render_bootstrap(bootstrap.read_text()))
    restore_runtime=source/'scripts/restore_runtime.py';text=restore_runtime.read_text()
    text=text.replace("    run(['docker','compose','build','backend'],cwd=base/'infra',env=env,check=True)\n",'')
    text=text.replace("['docker','compose','run','--rm','--no-deps','--entrypoint'", "['docker','compose','run','--rm','--no-deps','--pull','never','--entrypoint'")
    restore_runtime.write_text(text)
    installer=source/'scripts/install_restore_host.py'
    installer.write_text('#!/usr/bin/env python3\nimport runpy,sys\nsys.path.insert(0,'+repr(str(RUNTIME/'scripts/access_release'))+')\nrunpy.run_path('+repr(str(RUNTIME/'scripts/access_release/restore_host.py'))+',run_name="__main__")\n')
    f6=source/'scripts/install_backup_f6.py';f6.write_text(render_f6_installer(f6.read_text()))
    timer=source/'scripts/systemd/homecontrol-post-boot-health.timer'
    timer.write_text(timer.read_text().replace('OnBootSec=3min\n','OnBootSec=3min\nOnActiveSec=3min\n').replace('OnUnitActiveSec=10min','OnUnitInactiveSec=10min'))
    worker=source/'scripts/backup_archive_worker.sh';text=worker.read_text()
    text=text.replace("    --exclude 'postgres/data' \\\n", "    --exclude 'ssh/"+NAME+"/images' \\\n    --exclude 'postgres/data' \\\n")
    marker='# ---------- 8) Manifest + checksum ----------'
    text=text.replace(marker,'# Include exact images and private job receipts before sealing the archive.\n'
        'python3 "$CODE_DIR/access_release/backup_assets.py" "$BACKUP_DIR"\n'+marker)
    worker.write_text(text)
    for name,text in units(source).items():
        path=source/'units'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    manifest=dict(release=NAME,prepared=True,deployed=False,scope=['HC-35','HC-36','HC-41','HC-44','HC-45 required integration only'],
        excluded=[],previous_images={s:rows[s]['Image'] for s in SERVICES},images={},
        network=dict(name=network_name,subnet=subnet,gateway=gateway,broker_ip=broker_ip,ipv6=False,fixed_endpoints=endpoints),
        source_sha256={},private_sha256={},remaining_manual=['ESP identity/fixed IP confirmation tomorrow','Supervised deployment and physical telemetry/STOP/ack checks'],
        runtime=str(RUNTIME),private_runtime=str(PRIVATE))
    write_json(destination/'release.json',manifest,0o644)
    return manifest


def build(destination):
    root=Path(destination);source=root/'source';manifest=json.loads((root/'release.json').read_text())
    if 'HC-35' in manifest.get('scope',[]) and 'frontend' not in manifest['images']:
        raise ValueError('Build the matching HC-35/36 frontend before sealing Python images')
    logs=root/'evidence';logs.mkdir(exist_ok=True)
    specs={'backend':('infra/backend',BACKEND_FILES)}
    specs.update({s:('apps/'+folder,names) for s,(folder,names) in APPS.items()})
    for service,(directory,names) in specs.items():
        context=root/'builds'/service;context.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copyfile(source/directory/name,context/name)
        base_tag='hc-access-base-'+service.replace('_','-')+':20261030'
        run(['docker','tag',manifest['previous_images'][service],base_tag])
        dockerfile='FROM '+base_tag+'\nUSER root\nCOPY '+' '.join(names)+' /app/\n'
        if service=='backend':dockerfile+='RUN groupadd --gid 10001 homecontrol && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp homecontrol\nUSER 10001:10001\nENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp\n'
        (context/'Dockerfile').write_text(dockerfile)
        tag='homecontrol-'+('ingest' if service=='hc_ingest' else service.removeprefix('homecontrol-'))+':'+NAME
        process=subprocess.run(['docker','build','--network','none','--pull=false','-t',tag,str(context)],capture_output=True)
        (logs/(service+'-build.log')).write_bytes(process.stdout+process.stderr)
        if process.returncode:raise RuntimeError('Offline image build failed: '+service)
        image=json.loads(run(['docker','image','inspect',tag],text=True))[0]['Id'];manifest['images'][service]=image
    model=json.loads((source/'runtime.compose.json').read_text())
    for service,image in manifest['images'].items():model['services'][service]['image']=image
    (source/'runtime.compose.json').write_text(json.dumps(model,indent=2)+'\n')
    if 'HC-35' in manifest.get('scope',[]):
        write_json(source/'binding-release.json',dict(findings=['HC-35','HC-36'],
            backend_image=manifest['images']['backend'],frontend_image=manifest['images']['frontend']),0o644)
    export_images(root,manifest)
    return manifest


def build_frontend(destination,dist):
    root=Path(destination);dist=Path(dist).resolve()
    if not (dist/'index.html').is_file() or any(p.is_symlink() for p in dist.rglob('*')):
        raise ValueError('A regular, validated frontend build is required')
    manifest=json.loads((root/'release.json').read_text())
    context=root/'builds/frontend';context.mkdir(parents=True,exist_ok=True)
    shutil.copytree(dist,context/'dist',dirs_exist_ok=True)
    base_tag='hc-access-base-frontend:20261031'
    run(['docker','tag',manifest['previous_images']['frontend'],base_tag])
    (context/'Dockerfile').write_text('FROM '+base_tag+'\nUSER root\nRUN rm -rf /usr/share/nginx/html/*\nCOPY dist/ /usr/share/nginx/html/\n')
    tag='homecontrol-frontend:'+NAME
    result=subprocess.run(['docker','build','--network','none','--pull=false','-t',tag,str(context)],capture_output=True)
    (root/'evidence/frontend-build.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Offline frontend image build failed')
    manifest['images']['frontend']=json.loads(run(['docker','image','inspect',tag],text=True))[0]['Id']
    model=json.loads((root/'source/runtime.compose.json').read_text())
    model['services']['frontend']['image']=manifest['images']['frontend']
    write_json(root/'source/runtime.compose.json',model,0o644)
    write_json(root/'release.json',manifest,0o644)
    return manifest


def export_images(root,manifest):
    root=Path(root)
    model=json.loads((root/'source/runtime.compose.json').read_text())
    # Include exact old and new images, plus infrastructure images for fresh restore.
    image_ids=set(manifest['images'].values())|set(manifest['previous_images'].values())
    image_ids.update(v['image'] for v in model['services'].values() if v.get('image','').startswith('sha256:'))
    images=root/'private/runtime/images';images.mkdir(exist_ok=True)
    archive=images/'access-images.tar.gz'
    saver=subprocess.Popen(['docker','save',*sorted(image_ids)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    gzip=subprocess.Popen(['gzip','-1'],stdin=saver.stdout,stdout=archive.open('wb'),stderr=subprocess.PIPE);saver.stdout.close()
    gzip.communicate();saver.stderr.read()
    if gzip.returncode or saver.wait():raise RuntimeError('Offline image export failed')
    write_json(images/'manifest.json',dict(images=sorted(image_ids),archive=archive.name,sha256=digest(archive)))
    manifest['offline_image_archive_sha256']=digest(archive)
    write_json(root/'release.json',manifest,0o644)
    return manifest


def seal(destination):
    root=Path(destination);manifest=json.loads((root/'release.json').read_text())
    manifest['source_sha256']={str(p.relative_to(root/'source')):digest(p) for p in (root/'source').rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    manifest['private_sha256']={str(p.relative_to(root/'private')):digest(p) for p in (root/'private').rglob('*') if p.is_file() and '/images/' not in str(p)}
    write_json(root/'release.json',manifest,0o644)


def confirm_esp(destination, approval_file):
    """Finalize only a user-confirmed address; no live file, unit or container changes."""
    from install import approval
    confirmed=approval(approval_file);root=Path(destination)
    from secrets_bundle import prepare as bundle
    encrypted=root/'private/homecontrol-secrets-access.tar.gz.age'
    previous=encrypted.with_name('pre-confirmation-secrets.tar.gz.age')
    if previous.exists():raise ValueError('ESP finalization already attempted; reconcile before retry')
    policy=root/'private/runtime/network-policy.json';value=json.loads(policy.read_text())
    value.update(esp_ip=confirmed['esp_ip'],esp_confirmed=True);write_json(policy,value)
    if encrypted.exists():encrypted.rename(previous)
    bundle(root);seal(root)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('step',choices=('freeze','build','frontend','seal','confirm-esp'));parser.add_argument('--directory',type=Path,default=BASE/'backups/releases'/NAME);parser.add_argument('--approval',type=Path);parser.add_argument('--dist',type=Path)
    args=parser.parse_args()
    try:
        if args.step=='confirm-esp':
            if not args.approval:raise ValueError('Explicit ESP identity/stable address confirmation required')
            result=confirm_esp(args.directory,args.approval)
        elif args.step=='frontend':
            if not args.dist:raise ValueError('Explicit validated frontend --dist required')
            result=build_frontend(args.directory,args.dist)
        else:result={'freeze':freeze,'build':build,'seal':seal}[args.step](args.directory)
        print(json.dumps(dict(step=args.step,release=NAME,deployed=False)))
    except Exception as exc:raise SystemExit('Access preparation failed ('+type(exc).__name__+'); secret values withheld')
