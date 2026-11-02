"""Stop only our guarded lab if storage reserve is threatened; never touch production."""
import json,shutil,subprocess,time
from pathlib import Path
import lab_vm
OUT=Path(__file__).resolve().parent
report={'ok':True,'root_reserve_bytes':7*1024**3,'data_reserve_bytes':3*1024**3,
 'overlay_stop_bytes':39*1024**3,'peak_root_overlay_bytes':0,'peak_data_overlay_bytes':0,
 'minimum_root_free_bytes':None,'minimum_data_free_bytes':None,'lab_stopped_for_capacity':False}
for _ in range(2160):
 try:lab_vm.inspect()
 except subprocess.CalledProcessError:break
 root=shutil.disk_usage(lab_vm.ROOT).free;data=shutil.disk_usage(lab_vm.DATA).free
 a=(lab_vm.ROOT/'vm/os.qcow2').stat().st_blocks*512;b=(lab_vm.DATA/'work.qcow2').stat().st_blocks*512
 for key,value in [('root',root),('data',data)]:
  k='minimum_'+key+'_free_bytes';report[k]=value if report[k] is None else min(report[k],value)
 report['peak_root_overlay_bytes']=max(report['peak_root_overlay_bytes'],a);report['peak_data_overlay_bytes']=max(report['peak_data_overlay_bytes'],b)
 if root<report['root_reserve_bytes'] or data<report['data_reserve_bytes'] or a>report['overlay_stop_bytes']:
  lab_vm.inspect();subprocess.run(['docker','kill',lab_vm.NAME],check=True,stdout=subprocess.DEVNULL)
  report.update(ok=False,lab_stopped_for_capacity=True);break
 (OUT/'capacity-watch.json').write_text(json.dumps(report,indent=2)+'\n')
 time.sleep(5)
else:
 lab_vm.inspect();subprocess.run(['docker','kill',lab_vm.NAME],check=True,stdout=subprocess.DEVNULL)
 report.update(ok=False,lab_stopped_for_timeout=True)
(OUT/'capacity-watch.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
