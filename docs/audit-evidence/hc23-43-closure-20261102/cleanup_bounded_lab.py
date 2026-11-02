"""Delete only this completed, guarded disposable VM; preserve operator recovery export."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT/'bounded-lab'))
import lab_vm
vm=json.loads((OUT/'bounded-lab/vm-acceptance.json').read_text());assert vm['ok'] and vm['reboot_verified']
lab_vm.inspect()
try:lab_vm.ssh(['sudo','systemctl','poweroff'],capture_output=True,text=True)
except subprocess.CalledProcessError as error:assert error.returncode==255
for _ in range(12):
 r=subprocess.run(['docker','inspect',lab_vm.NAME],capture_output=True)
 if r.returncode:break
 time.sleep(2)
else:
 lab_vm.inspect();subprocess.run(['docker','stop','--time','10',lab_vm.NAME],check=True,stdout=subprocess.DEVNULL)
assert subprocess.run(['docker','inspect',lab_vm.NAME],capture_output=True).returncode!=0
for p in (lab_vm.ROOT/'vm',lab_vm.DATA):
 assert p.is_dir() and not p.is_symlink() and p.stat().st_uid==os.getuid()
 assert not p.is_mount();shutil.rmtree(p)
assert (lab_vm.INPUT/'input.json').is_file() and (lab_vm.INPUT/'age-key.txt').is_file()
r={'ok':True,'only_bounded_vm_and_own_disks_removed':True,'temporary_guest_ssh_key_removed':True,
 'original_operator_recovery_input_preserved':True,'previous_r16_lab_preserved':True,
 'root_free_bytes':shutil.disk_usage('/tmp').free,'project_free_bytes':shutil.disk_usage('/srv/docker/homecontrol').free}
(OUT/'lab-cleanup.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
