import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/srv/docker/homecontrol/scripts/access_release')
from network import execute
processes=[]
def run(args,**kw):
 r=subprocess.run(args,capture_output=True,text=True,**kw)
 if r.returncode:raise RuntimeError(str(args[:3])+': '+r.stderr[:300])
 return r.stdout
def inside(pid,args):return run(['nsenter','-t',str(pid),'-n',*args])
def namespace(name,bridge,addresses,gateway=None):
 process=subprocess.Popen(['unshare','-n','sleep','120']);processes.append(process);time.sleep(.05)
 a='v'+name;b='p'+name
 run(['ip','link','add',a,'type','veth','peer','name',b]);run(['ip','link','set',a,'master',bridge]);run(['ip','link','set',a,'up']);run(['ip','link','set',b,'netns',str(process.pid)])
 inside(process.pid,['ip','link','set','lo','up']);inside(process.pid,['ip','link','set',b,'up'])
 for address in addresses:inside(process.pid,['ip','address','add',address,'dev',b])
 if gateway:inside(process.pid,['ip','route','add','default','via',gateway])
 return process.pid
server_code='''import socket,threading,time
for port in (1883,1884):
 s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('0.0.0.0',port));s.listen()
 def serve(listener):
  while True:
   peer,_=listener.accept();peer.close()
 threading.Thread(target=serve,args=(s,),daemon=True).start()
time.sleep(110)
'''
probe_code='''import socket,sys
s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET);s.settimeout(.4)
if sys.argv[3]!='-':s.bind((sys.argv[3],0))
try:s.connect((sys.argv[1],int(sys.argv[2])));print('yes')
except OSError:print('no')
finally:s.close()
'''
def probe(pid,target,port=1883,source='-'):
 args=[sys.executable,'-c',probe_code,target,str(port),source]
 return (inside(pid,args) if pid else run(args)).strip()=='yes'
try:
 run(['ip','link','set','lo','up'])
 for bridge,address in [('lan','192.168.1.133/24'),('brtest','172.19.0.1/24')]:
  run(['ip','link','add',bridge,'type','bridge']);run(['ip','address','add',address,'dev',bridge]);run(['ip','link','set',bridge,'up'])
 # These forwarding settings exist only inside this disposable network namespace.
 Path('/proc/sys/net/ipv4/ip_forward').write_text('1')
 esp=namespace('esp','lan',['192.168.1.179/24'],'192.168.1.133')
 other=namespace('other','lan',['192.168.1.89/24','192.168.1.90/24','fd00::89/64'],'192.168.1.133')
 broker=namespace('broker','brtest',['172.19.0.9/24'],'172.19.0.1')
 docker=namespace('docker','brtest',['172.19.0.5/24'],'172.19.0.1')
 run(['ip','-6','address','add','fd00::133/64','dev','lan'])
 server=subprocess.Popen(['nsenter','-t',str(broker),'-n',sys.executable,'-c',server_code]);processes.append(server)
 v6=subprocess.Popen([sys.executable,'-c',"import socket,time;s=socket.socket(socket.AF_INET6);s.bind(('::',1883));s.listen();time.sleep(110)"]);processes.append(v6)
 run(['nft','-f','-'],input='add table ip fixture\nadd chain ip fixture nat {type nat hook prerouting priority -100;policy accept;}\nadd rule ip fixture nat ip daddr 192.168.1.133 tcp dport 1883 dnat to 172.19.0.9:1883\n')
 time.sleep(.3)
 assert probe(esp,'192.168.1.133') and probe(other,'172.19.0.9',source='192.168.1.90') and probe(docker,'172.19.0.9') and probe(None,'172.19.0.9')
 policy=dict(esp_ip='192.168.1.179',broker_ip='172.19.0.9',docker_subnet='172.19.0.0/24',dashboard_ip='192.168.1.89',mode='authenticated',owned_chain=False)
 execute(policy);policy['owned_chain']=True
 assert probe(esp,'192.168.1.133')
 assert not probe(other,'172.19.0.9',source='192.168.1.90')
 assert not probe(docker,'172.19.0.9')
 assert not probe(None,'172.19.0.9')
 assert not probe(other,'fd00::133')
 assert probe(docker,'172.19.0.9',1884)
 execute(policy)
 assert probe(esp,'192.168.1.133') and not probe(docker,'172.19.0.9')
 policy['mode']='rollback';execute(policy)
 assert probe(docker,'172.19.0.9') and probe(None,'172.19.0.9') and probe(other,'172.19.0.9',source='192.168.1.89')
 assert not probe(other,'172.19.0.9',source='192.168.1.90')
 assert probe(esp,'192.168.1.133')
 result=dict(success=True,esp_dnat_allowed=True,other_lan_denied=True,direct_docker_peer_denied=True,host_denied=True,ipv6_proxy_path_denied=True,authenticated_port_unchanged=True,idempotent_reapply=True,rollback_internal_and_dashboard_allowed=True,rollback_foreign_lan_still_denied=True,production_rules_changed=False,namespace='unshare -Urn')
 Path('/tmp/hc-access-r10-20261030/network-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 for p in reversed(processes):
  p.terminate()
 for p in reversed(processes):
  try:p.wait(timeout=2)
  except subprocess.TimeoutExpired:p.kill();p.wait()
