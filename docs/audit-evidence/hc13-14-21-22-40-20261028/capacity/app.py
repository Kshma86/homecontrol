import ast,json,time,threading
from pathlib import Path
from types import SimpleNamespace
from flask import Flask,request,jsonify,g
from flask_sock import Sock
from worker_runtime import RequestCapacity
from tests.test_startup_service import StartupServiceTest
app=Flask(__name__);sock=Sock(app);_REQUEST_CAPACITY=RequestCapacity()
startup=StartupServiceTest().service([],False)
startup.ensure_started()
def get_startup_service():return startup
def get_robot_service():return SimpleNamespace(map_url=lambda x:None)
def get_irrigation_service():return SimpleNamespace(pump_current_live_snapshot=lambda:{'source_received_at_epoch':None})
x10_monitor=SimpleNamespace(value=lambda key:None)
tree=ast.parse(Path('/source/app.py').read_text())
names=('admit_long_request','release_long_request','xiaomi_x10_live_socket','irrigation_pump_current_live_socket')
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'/source/app.py','exec'),globals())
@app.get('/health')
def health():return jsonify(ok=True)
@app.get('/workers')
def workers():return jsonify(startup.status())
@app.post('/api/ai/chat')
@app.post('/api/backup/create')
@app.get('/api/debug/logs')
def slow():
 time.sleep(4)
 return jsonify(ok=True)
def shutdown_backend(timeout=8):
 stopped=startup.stop(timeout)
 Path('/evidence/shutdown.json').write_text(json.dumps({'stop_called':True,'stopped':stopped,'alive':[n for n,t in startup._threads.items() if t.is_alive()]}))
 return stopped
