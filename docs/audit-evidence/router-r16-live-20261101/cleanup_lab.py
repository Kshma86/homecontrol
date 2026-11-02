#!/usr/bin/env python3
"""Delete only delegated input copies and the stopped disposable HC guest disk."""
from datetime import datetime,timezone
import json,shutil,subprocess,time
from pathlib import Path
import lab_vm
OUT=Path(__file__).resolve().parent
report=json.loads((OUT/'vm-acceptance.json').read_text())
assert report['ok'] and report['reboot_verified'] and not report['fresh']['candidate_fixes_applied']
assert json.loads((OUT/'git-verification.json').read_text())['ok']
root=lab_vm.ROOT
assert str(root)=='/tmp/hc-router-audit-20261101' and root.is_dir() and not root.is_symlink()
lab_vm.inspect()
try:
 lab_vm.ssh(['sudo','systemctl','poweroff'],capture_output=True,text=True)
except subprocess.CalledProcessError as e:
 assert e.returncode==255
for _ in range(60):
 running=subprocess.run(['docker','inspect',lab_vm.NAME],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if running.returncode: break
 time.sleep(1)
else: raise RuntimeError('Guest container has not stopped; private files were not removed')
inputs=root/'input'; disk=root/'vm/os.qcow2'; key=root/'vm/id_ed25519'
assert inputs.is_dir() and not inputs.is_symlink() and disk.is_file() and not disk.is_symlink()
assert key.is_file() and not key.is_symlink()
shutil.rmtree(inputs)
disk.unlink();key.unlink()
assert not inputs.exists() and not disk.exists() and not key.exists()
value=dict(ok=True,finished_at=datetime.now(timezone.utc).isoformat(),guest_stopped=True,
 hc_guest_disk_removed=True,delegated_repository_git_and_age_key_copies_removed=True,
 disposable_ssh_private_key_removed=True,production_paths_not_modified=True,
 clean_os_base_without_hc_data_retained=True)
(OUT/'lab-cleanup.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps(value))
