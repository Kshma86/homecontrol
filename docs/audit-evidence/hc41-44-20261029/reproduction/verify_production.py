import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path

base=Path('/srv/docker/homecontrol')
evidence=Path('/tmp/hc41-44-20261029')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inspect(names):
    template='{{json .Name}}\t{{json .Id}}\t{{json .Image}}\t{{json .State.StartedAt}}\t{{json .RestartCount}}'
    raw=subprocess.check_output(['docker','inspect','--format',template,*names],text=True)
    return [dict(zip(('Name','Id','Image','StartedAt','RestartCount'),map(json.loads,line.split('\t')))) for line in raw.splitlines()]
before=json.loads((evidence/'live-before.json').read_text())
after=inspect([r['Name'] for r in before])
changes=[{'name':a['Name'],'before':b,'after':a} for b,a in zip(before,after) if b!=a]
release=json.loads((base/'backups/releases/hc-ingest-20261028-r9/release.json').read_text())
protected=release['active_host_sha256']
changed_host=[p for p,h in protected.items() if sha(base/p)!=h]
baseline=json.loads((evidence/'before-sha256.json').read_text())
unchanged_paths=['infra/mqtt/config/mosquitto.conf','infra/backend/mqtt_monitor_service.py',
    'apps/hc_ingest/mqtt_ingest_multi.py','apps/gree-climate/gree_climate_bridge.py',
    'apps/xiaomi-x10/xiaomi_x10_bridge.py','apps/xiaomi-x10/xiaomi_x10_api.py',
    'apps/ha-growatt-poller/ha_growatt_poller.py','apps/tuya-poller/tuya_poller.py']
unchanged={p:sha(base/p)==baseline[p] for p in unchanged_paths}
exposure=json.loads((evidence/'exposure-before.json').read_text())
user=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .Config.User}}','homecontrol-backend']))
configured_user=user
user=user or 'root'  # Docker's empty Config.User means the image's default root.
mounts=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .Mounts}}','homecontrol-backend']))
mounts=[dict(source=m['Source'],destination=m['Destination'],rw=m['RW']) for m in mounts]
ports=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .HostConfig.PortBindings}}','homecontrol-mqtt']))
lab=subprocess.check_output(['docker','ps','-a','--filter','name=hc44-lab-','--format','{{.Names}}'],text=True).splitlines()
override=str((base/'infra/docker-compose.override.yml').resolve())
audit_sha=sha(base/'HC_REFACTOR_AUDIT.md')
safety_sha=sha(base/'infra/backend/combustion_safety_service.py')
result=dict(checked_at=datetime.now(timezone.utc).isoformat(),deployed=False,
    container_count=len(before),unchanged_container_count=len(before)-len(changes),container_changes=changes,
    protected_host_count=len(protected),changed_protected_host_files=changed_host,
    unchanged_mqtt_and_bridge_sources=unchanged,backend_config_user=configured_user,backend_runtime_user=user,
    backend_runtime_user_unchanged=user==exposure['backend_user'],
    backend_mounts_unchanged=sorted(mounts,key=lambda m:m['destination'])==sorted(exposure['backend_mounts'],key=lambda m:m['destination']),
    mqtt_bindings_unchanged=ports==exposure['mqtt_ports'],
    active_override=override,active_override_is_r9=override.endswith('/hc-ingest-20261028-r9/release.override.json'),
    audit_sha256=audit_sha,audit_unchanged=audit_sha=='51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2',
    safety_sha256=safety_sha,safety_unchanged=safety_sha=='7334974829abd6c9497b6bda41190c25967751e2490b6e6824ba0fe28183a2c6',
    remaining_lab_containers=lab,
    hostops_service_installed=Path('/etc/systemd/system/homecontrol-hostops.service').exists(),
    production_hostops_socket_exists=Path('/run/homecontrol-hostops/operations.sock').exists())
(evidence/'production-unchanged.json').write_text(json.dumps(result,indent=2)+'\n')
assert not changes and not changed_host and all(unchanged.values()) and not lab
assert all(result[k] for k in ('backend_runtime_user_unchanged','backend_mounts_unchanged','mqtt_bindings_unchanged','active_override_is_r9','audit_unchanged','safety_unchanged'))
assert not result['hostops_service_installed'] and not result['production_hostops_socket_exists']
print(json.dumps(result,indent=2))
