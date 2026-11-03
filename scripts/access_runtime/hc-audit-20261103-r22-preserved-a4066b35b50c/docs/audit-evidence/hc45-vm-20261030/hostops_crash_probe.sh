python3 - <<'PY'
import subprocess,json,time
from pathlib import Path
p=Path('/run/homecontrol-hostops');before=p.stat().st_ino
old=int(subprocess.check_output(['systemctl','show','homecontrol-hostops.service','-p','MainPID','--value'],text=True))
subprocess.run(['systemctl','kill','--kill-who=main','--signal=SIGKILL','homecontrol-hostops.service'],check=True)
code='from host_operations_client import HostOperationsClient;assert HostOperationsClient().call("containers")'
for _ in range(60):
 pid=int(subprocess.check_output(['systemctl','show','homecontrol-hostops.service','-p','MainPID','--value'],text=True))
 r=subprocess.run(['docker','exec','homecontrol-backend','python','-c',code],capture_output=True)
 if pid not in (0,old) and r.returncode==0:break
 time.sleep(.25)
else:raise AssertionError('Actual SIGKILL restart did not recover IPC')
assert before==p.stat().st_ino
result={'ok':True,'real_sigkill':True,'automatic_systemd_restart':True,'directory_inode_preserved':True,'backend_rpc_recovered_without_container_restart':True}
Path('/lab/hostops-crash-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
PY
