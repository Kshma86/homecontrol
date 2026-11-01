import json,pathlib,subprocess,tempfile
B=pathlib.Path('/srv/docker/homecontrol');D=B/'docs/audit-evidence/hc32-23-43-20261031';net='hc-f10-queue-net';broker='hc-f10-queue-broker';worker='hc-f10-queue-client'
model=json.loads((B/'scripts/access_runtime/hc-access-20261030-r10/runtime.compose.json').read_text())
owned=False;broker_created=False
for existing in (broker,worker):
 if subprocess.run(['docker','inspect','--type','container',existing],capture_output=True).returncode==0:
  raise RuntimeError('Lab name already in use; do not remove an unowned container')
with tempfile.TemporaryDirectory(prefix='hc32-broker-') as folder:
 config=pathlib.Path(folder)/'mosquitto.conf';config.write_text('listener 1883\nallow_anonymous true\npersistence false\nlog_type warning\n');pathlib.Path(folder).chmod(0o755);config.chmod(0o644)
 try:
  subprocess.run(['docker','network','create','--internal',net],check=True,capture_output=True);owned=True
  subprocess.run(['docker','run','-d','--name',broker,'--network',net,'--read-only','--mount','type=bind,src='+str(config)+',dst=/mosquitto/config/mosquitto.conf,readonly',model['services']['mqtt']['image']],check=True,capture_output=True);broker_created=True
  cmd=['docker','run','--rm','--name',worker,'--network',net,'--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--user','10001:10001','--mount','type=bind,src='+str(B/'apps')+',dst=/work/apps,readonly','--mount','type=bind,src='+str(D/'command_broker_probe.py')+',dst=/probe.py,readonly','--entrypoint','python',json.loads((D/'build-results.json').read_text())['tuya-poller']['image'],'/probe.py']
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
  (D/'command-broker.log').write_text(r.stdout+r.stderr)
  print(r.stdout);print('probe_exit',r.returncode)
  if r.returncode:print(r.stderr[-2200:])
  assert r.returncode==0
  line=next(x for x in r.stdout.splitlines() if x.startswith('HC12_BROKER_RESULT='));(D/'command-broker.json').write_text(json.dumps(json.loads(line.split('=',1)[1]),indent=2)+'\n')
 finally:
  # Remove only names owned by this isolated probe, never production services.
  if broker_created:
   subprocess.run(['docker','rm','-f',worker],capture_output=True)
   subprocess.run(['docker','rm','-f',broker],capture_output=True)
  if owned:subprocess.run(['docker','network','rm',net],capture_output=True)
