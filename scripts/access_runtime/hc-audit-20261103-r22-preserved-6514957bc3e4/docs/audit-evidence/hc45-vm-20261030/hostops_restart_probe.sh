python3 - <<'PY'
import subprocess,json,time
from pathlib import Path
sock=Path('/run/homecontrol-hostops')
before=sock.stat().st_ino
subprocess.run(['systemctl','restart','homecontrol-hostops.service'],check=True)
code='from host_operations_client import HostOperationsClient;print(len(HostOperationsClient().call("containers")))'
for attempt in range(40):
 r=subprocess.run(['docker','exec','homecontrol-backend','python','-c',code],capture_output=True,text=True)
 if r.returncode==0:break
 time.sleep(.25)
result={'before_directory_inode':before,'after_directory_inode':sock.stat().st_ino,'rpc_after_service_restart':r.returncode==0}
Path('/lab/hostops-restart-probe.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
if r.returncode:print(r.stderr[-1800:])
assert r.returncode==0,'Host executor restart detached the backend socket mount'
PY
