import concurrent.futures,json,time
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.error import HTTPError
import websocket
base='http://127.0.0.1:5050'
def request(path,method='GET'):
 start=time.monotonic()
 try:
  with urlopen(Request(base+path,method=method,data=b'{}' if method=='POST' else None),timeout=6) as r: r.read();status=r.status
 except HTTPError as e:status=e.code
 return status,(time.monotonic()-start)*1000
for _ in range(30):
 try:
  assert request('/health')[0]==200;break
 except Exception:time.sleep(.1)
else:raise AssertionError('fixture not ready')
a=websocket.create_connection('ws://127.0.0.1:5050/api/irrigation/pump-current/live',timeout=2)
b=websocket.create_connection('ws://127.0.0.1:5050/api/xiaomi-x10/live',timeout=2)
try:
 try:
  extra=websocket.create_connection('ws://127.0.0.1:5050/api/xiaomi-x10/live',timeout=2)
 except websocket.WebSocketBadStatusException as e:assert e.status_code==503
 else:extra.close();raise AssertionError('third WS accepted')
 with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
  long=[executor.submit(request,p,m) for p,m in [('/api/ai/chat','POST'),('/api/backup/create','POST'),('/api/debug/logs','GET')]]
  time.sleep(.15)
  assert request('/api/ai/chat','POST')[0]==503
  started=time.monotonic();controls=list(executor.map(lambda _:request('/health'),range(64)))
  elapsed=time.monotonic()-started
  assert all(s==200 for s,_ in controls),controls
  assert elapsed<2,elapsed
  assert all(f.result()[0]==200 for f in long)
 a.close();time.sleep(.4)
 a=websocket.create_connection('ws://127.0.0.1:5050/api/irrigation/pump-current/live',timeout=2)
 durations=sorted(ms for _,ms in controls)
 result={'websocket_clients':2,'slow_ai_backup_diagnostic':3,'control_requests':len(controls),'control_all_200':True,'control_p95_ms':round(durations[int(.95*(len(durations)-1))],2),'control_batch_sec':round(elapsed,3),'extra_websocket_503':True,'extra_ai_503':True,'silent_pump_disconnect_frees_capacity':True}
 Path('/evidence/capacity-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:a.close();b.close()
