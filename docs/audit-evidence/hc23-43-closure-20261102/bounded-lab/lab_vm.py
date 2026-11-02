"""Only the new r18 closure guest: no host Docker socket, LAN or production mounts."""
import json,shlex,subprocess,shutil
from pathlib import Path
ROOT=Path('/tmp/hc23-closure2-20261102')
DATA=Path('/srv/docker/homecontrol/backups/audit-labs/hc23-closure-20261102')
INPUT=Path('/tmp/hc-security-audit-20261102/input')
BASE=Path('/tmp/hc-router-audit-20261101/vm')
NAME='hc-r18-closure-lab2-20261102'
LABEL='hc23-closure-bounded-20261102'
IMAGE='sha256:f7f7c3d3d8ad4ab720d75a473f96a7a8f5daf53495ba679505aafe8f945c8ec2'
def call(args,**kw):return subprocess.run(args,check=True,**kw)
def inspect():
 v=json.loads(subprocess.check_output(['docker','inspect',NAME],text=True))[0]
 assert v['Config']['Labels'].get('hc.audit')==LABEL
 assert v['HostConfig']['NetworkMode']=='none' and not v['HostConfig']['Privileged']
 assert v['Config']['User']=='1000:1000'
 allowed={'/vm':(str(ROOT/'vm'),True),'/vm/input':(str(INPUT),False),'/base':(str(BASE),False),'/labdata':(str(DATA),True)}
 for m in v['Mounts']:
  if m['Type']=='tmpfs':assert m['Destination'] in ('/tmp','/var/lib/postgresql/data')
  else:assert m['Type']=='bind' and allowed[m['Destination']]==(m['Source'],m['RW'])
 assert 'user,id=n0,restrict=on,hostfwd=tcp:127.0.0.1:22247-:22' in v['Args']
 return v

def ssh(args,**kw):
 inspect()
 return call(['docker','exec','-i',NAME,'ssh','-i','/vm/id_ed25519','-p','22247',
 '-o','UserKnownHostsFile=/vm/known_hosts','-o','StrictHostKeyChecking=yes','-o','BatchMode=yes',
 '-o','ConnectTimeout=5','lab@127.0.0.1',shlex.join(args)],**kw)

def capacity_guard():
 assert shutil.disk_usage('/tmp').free >= 48*1024**3, 'Need 48 GiB free on root (40 GiB disk cap plus 8 GiB reserve)'
 assert shutil.disk_usage(DATA).free >= 22*1024**3, 'Need 22 GiB free on lab data volume'

def start():
 capacity_guard()
 receipt=json.loads((INPUT/'input.json').read_text());assert receipt['ok'] and receipt['release']=='hc-security-20261102-r18'
 assert (ROOT/'vm/os.qcow2').is_file() and (ROOT/'vm/seed.iso').is_file()
 assert not subprocess.run(['docker','inspect',NAME],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 args=['docker','run','-d','--rm','--name',NAME,'--label','hc.audit='+LABEL,'--network','none','--user','1000:1000',
 '--ulimit','fsize=42949672960:42949672960','--group-add',str(Path('/dev/kvm').stat().st_gid),'--device','/dev/kvm','--cap-drop','ALL','--security-opt','no-new-privileges',
 '--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=64m','--tmpfs','/var/lib/postgresql/data:rw,nosuid,nodev,size=1m',
 '--mount','type=bind,src='+str(ROOT/'vm')+',dst=/vm','--mount','type=bind,src='+str(INPUT)+',dst=/vm/input,readonly',
 '--mount','type=bind,src='+str(BASE)+',dst=/base,readonly','--mount','type=bind,src='+str(DATA)+',dst=/labdata',IMAGE,'qemu-system-x86_64','-machine','accel=kvm','-cpu','host','-m','6144','-smp','2',
 '-drive','file=/vm/os.qcow2,format=qcow2,if=virtio,discard=unmap,detect-zeroes=unmap','-drive','file=/labdata/work.qcow2,format=qcow2,if=virtio,discard=unmap,detect-zeroes=unmap','-drive','file=/vm/seed.iso,media=cdrom,readonly=on',
 '-virtfs','local,path=/vm/input,security_model=none,mount_tag=hc_input,readonly=on',
 '-netdev','user,id=n0,restrict=on,hostfwd=tcp:127.0.0.1:22247-:22','-device','virtio-net-pci,netdev=n0','-nographic']
 call(args,stdout=subprocess.DEVNULL);inspect()
