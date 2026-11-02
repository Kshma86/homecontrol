import subprocess,sys,shlex
SSH=['docker','exec','-i','hc-restore-vm','ssh','-i','/vm/id_ed25519','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/vm/known_hosts','-o','ConnectTimeout=5','-p','22245','lab@127.0.0.1']
GUARD='set -euo pipefail\n[ "$(hostname)" = hc-restore-vm ]\n[ "$(systemd-detect-virt)" = kvm ]\n'
def run(script,**kwargs):return subprocess.run(SSH+[shlex.join(['sudo','bash','-c',GUARD+script])],input=b'',**kwargs)
if __name__=='__main__':
 if len(sys.argv)==3 and sys.argv[1]=='script':raise SystemExit(run(open(sys.argv[2]).read()).returncode)
 if len(sys.argv)==3 and sys.argv[1]=='put':
  with open(sys.argv[2],'rb') as f:r=subprocess.run(SSH+['sudo','tar','xf','-','-C','/'],stdin=f)
  raise SystemExit(r.returncode)
 raise SystemExit('script FILE or put PRIVATE_TAR only')
