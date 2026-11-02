"""Prepare a fresh writable overlay over the already verified empty-OS image."""
import json,os,shutil,subprocess,time
from pathlib import Path
import lab_vm as vm
os.umask(0o077)
vm.DATA.mkdir(mode=0o700,parents=True,exist_ok=True)
assert not vm.DATA.is_symlink() and vm.DATA.stat().st_uid==os.geteuid()
vm.capacity_guard()
vm.ROOT.mkdir(mode=0o700,exist_ok=True)
(vm.ROOT/'vm').mkdir(mode=0o700,exist_ok=True)
assert not vm.ROOT.is_symlink() and vm.ROOT.stat().st_uid==os.geteuid()
assert subprocess.run(['docker','inspect',vm.NAME],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
def tool(args,base=False):
 cmd=['docker','run','--rm','--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges',
 '--mount','type=bind,src='+str(vm.ROOT/'vm')+',dst=/vm','--mount','type=bind,src='+str(vm.DATA)+',dst=/labdata']
 if base:cmd+=['--mount','type=bind,src='+str(vm.BASE)+',dst=/base,readonly']
 return subprocess.check_output(cmd+[vm.IMAGE,*args],text=True)
if not (vm.ROOT/'vm/id_ed25519').exists():
 tool(['ssh-keygen','-q','-t','ed25519','-N','','-f','/vm/id_ed25519'])
pub=(vm.ROOT/'vm/id_ed25519.pub').read_text().strip()
user='#cloud-config\nhostname: hc-router-restore-lab\nmanage_etc_hosts: true\nssh_pwauth: false\nusers:\n  - default\n  - name: lab\n    groups: [sudo, docker]\n    shell: /bin/bash\n    sudo: ALL=(ALL) NOPASSWD:ALL\n    ssh_authorized_keys:\n      - '+pub+'\n'
(vm.ROOT/'vm/user-data').write_text(user)
(vm.ROOT/'vm/meta-data').write_text('instance-id: hc23-r18-bounded-20261102\nlocal-hostname: hc-router-restore-lab\n')
tool(['genisoimage','-quiet','-output','/vm/seed.iso','-volid','cidata','-joliet','-rock','/vm/user-data','/vm/meta-data'])
shutil.copyfile(vm.BASE/'os-ready.qcow2',vm.ROOT/'vm/os-ready.qcow2')
tool(['qemu-img','rebase','-u','-f','qcow2','-F','qcow2','-b','/base/base.img','/vm/os-ready.qcow2'],base=True)
if (vm.ROOT/'vm/os.qcow2').exists(): (vm.ROOT/'vm/os.qcow2').unlink()
tool(['qemu-img','create','-f','qcow2','-F','qcow2','-b','/vm/os-ready.qcow2','/vm/os.qcow2'],base=True)
assert not (vm.DATA/'work.qcow2').exists()
tool(['qemu-img','create','-f','qcow2','/labdata/work.qcow2','18G'])
vm.start()
for attempt in range(60):
 scan=subprocess.run(['docker','exec',vm.NAME,'ssh-keyscan','-p','22247','127.0.0.1'],capture_output=True,text=True)
 if scan.returncode==0 and scan.stdout.strip():
  (vm.ROOT/'vm/known_hosts').write_text(scan.stdout)
  try:
   r=vm.ssh(['sudo','python3','-c',"import json,subprocess;from pathlib import Path;assert subprocess.check_output(['hostname'],text=True).strip()=='hc-router-restore-lab';assert subprocess.check_output(['systemd-detect-virt'],text=True).strip()=='kvm';assert Path('/lab/os-ready').exists();assert not Path('/srv/docker/homecontrol').exists();assert not subprocess.check_output(['docker','image','ls','-q'],text=True).strip();print(json.dumps({'empty_hc':True,'empty_image_store':True,'os_ready':True}))"],capture_output=True,text=True)
   print(r.stdout);break
  except subprocess.CalledProcessError:pass
 time.sleep(3)
else:raise TimeoutError('Fresh closure guest did not become ready')
Path(__file__).with_name('vm-preparation.json').write_text(json.dumps(dict(ok=True,container=vm.NAME,network='none',qemu_restrict=True,host_docker_socket=False,private_input_readonly=True,fresh_overlay=True,empty_hc=True,empty_image_store=True,hardware_network=False),indent=2)+'\n')
