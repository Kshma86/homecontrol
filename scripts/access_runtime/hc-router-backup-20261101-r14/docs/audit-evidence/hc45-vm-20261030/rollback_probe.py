import hashlib,json,os,subprocess,sys
from pathlib import Path
B=Path('/srv/docker/homecontrol');R=B/'scripts/access_runtime/hc-router-backup-20261101-r14'
assert subprocess.check_output(['hostname'],text=True).strip()=='hc-restore-vm' and os.geteuid()==0
sys.path[:0]=[str(R/'scripts'),str(R/'infra/backend')]
from install_backup_f6 import install
root=Path('/etc/systemd/system');probe=root/'homecontrol-backup.service';original=probe.read_bytes()
probe.write_bytes(original+b'\n# VM rollback previous-version sentinel\n')
subprocess.run(['systemctl','daemon-reload'],check=True)
names=[p.name for p in root.glob('homecontrol-*') if p.is_file()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={n:sha(root/n) for n in names}
watchers=['homecontrol-backup.timer','homecontrol-log-maintenance.timer','homecontrol-post-boot-health.timer','homecontrol-full-ai-backup-request.path','homecontrol-backup-apply.path']
def enabled(n):return subprocess.run(['systemctl','is-enabled',n],capture_output=True,text=True).stdout.strip()
states={n:enabled(n) for n in watchers};injected=False

def run(args,**kwargs):
 global injected
 if not injected and args[:3]==['systemctl','enable','--now'] and args[-1]=='homecontrol-backup.timer':
  injected=True;return subprocess.CompletedProcess(args,1,'','VM injected unit activation failure')
 return subprocess.run(args,**kwargs)
try:
 try:install(apply=True,root=B/'backups',fresh_host=True,restore_host=True,run=run)
 except RuntimeError:pass
 else:raise AssertionError('Injected failure was not reported')
 assert injected and before=={n:sha(root/n) for n in names}
 assert states=={n:enabled(n) for n in watchers}
 result={'ok':True,'real_systemd_manager':True,'fault':'one enable --now return code replaced; all other calls real','previous_unit_bytes_restored':True,'previous_enabled_states_restored':True,'sentinel_preserved_on_failed_transition':True,'unit_files_compared':len(names),'no_backup_started_by_probe':True}
 Path('/lab/unit-rollback.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 probe.write_bytes(original);subprocess.run(['systemctl','daemon-reload'],check=True)
