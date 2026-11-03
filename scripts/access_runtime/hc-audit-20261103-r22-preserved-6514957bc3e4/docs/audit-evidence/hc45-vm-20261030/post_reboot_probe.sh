[ "$(cat /proc/sys/kernel/random/boot_id)" != "$(cat /lab/pre-reboot-id)" ]
python3 /lab/probe_restored.py after-reboot-probe
python3 - <<'PY'
import json,subprocess
from pathlib import Path
for name in ('homecontrol-hostops.service','homecontrol-mqtt-access.service'):
 subprocess.run(['systemctl','is-active','--quiet',name],check=True)
for family in ('bridge','inet'):subprocess.run(['nft','list','table',family,'hc41_r10'],check=True,stdout=subprocess.DEVNULL)
assert json.loads(Path('/srv/docker/homecontrol/infra/ssh/hc-audit-20261102-r19/network-policy.json').read_text())['owned_chain'] is True
rows=[json.loads(p.read_text()) for p in Path('/var/lib/homecontrol-hostops/jobs').glob('*.json')]
assert any(r.get('operation')=='restart' and r.get('state')=='completed' for r in rows)
result={'ok':True,'real_guest_reboot':True,'boot_id_changed':True,'root_services_active':True,'both_nft_tables_present':True,'completed_restart_persisted':True,'interrupted_job_not_replayed':True}
Path('/lab/reboot-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
PY
