import importlib.util,json,os,subprocess,time
from pathlib import Path

ROOT=Path('/srv/docker/homecontrol');E=Path('/tmp/hc41-explorer-20261030')
spec=importlib.util.spec_from_file_location('hc41_prepare',ROOT/'scripts/prepare_mqtt_access.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
package=E/'lab-private'
if not package.exists():module.prepare(package,esp_ip='192.168.1.179')
name='hc41-explorer-lab-20261030'
def run(args,**kw):
    result=subprocess.run(args,capture_output=True,text=True,**kw)
    if result.returncode:
        (E/'lab-error.log').write_text(result.stdout+result.stderr)
        raise RuntimeError('Laboratory command failed; private lab-error.log contains details')
    return result.stdout
image='sha256:077fe4ff4c49df1e860c98335c77dda08360629e0e2a718147027e4db3eace9d'
try:
    # The hash utility sees only disposable random lab credentials, not a host socket.
    hashed=all(row.partition(':')[2].startswith('$') for row in (package/'credentials/passwords').read_text().splitlines())
    if not hashed:
        run(['docker','run','--rm','--network','none','--read-only','--user',str(os.getuid())+':'+str(os.getgid()),
            '--tmpfs','/tmp:rw,mode=1777','-w','/candidate/credentials','-v',str(package)+':/candidate','--entrypoint','mosquitto_passwd',image,'-U','/candidate/credentials/passwords'])
    run(['docker','run','-d','--name',name,'--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--user',str(os.getuid())+':'+str(os.getgid()),
        '--tmpfs','/mosquitto/data:rw,uid='+str(os.getuid())+',gid='+str(os.getgid())+',mode=0700',
        '-v',str(package)+':/mosquitto/config:ro','--entrypoint','mosquitto',image,'-c','/mosquitto/config/mosquitto.conf'])
    time.sleep(.3)
    result=run(['docker','run','--rm','--network','container:'+name,'--read-only','--tmpfs','/tmp:rw,size=32m',
        '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/work/infra/backend',
        '-v',str(ROOT)+':/work:ro','-v',str(E)+':/evidence','-v',str(package)+':/candidate:ro',
        '--user',str(os.getuid())+':'+str(os.getgid()),'--entrypoint','python',
        'homecontrol-backend:hc-read-models-20261028-r8','/evidence/broker_probe.py'])
    (E/'broker-tests.log').write_text(result)
    print(result)
finally:
    subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
