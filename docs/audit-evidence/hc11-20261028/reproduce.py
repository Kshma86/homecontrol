import ast,json,threading,time
from pathlib import Path
source=Path(__file__).with_name('baseline-connect-db.py');tree=ast.parse(source.read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');fn=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='connect_db')
started=threading.Event();stop=threading.Event();attempts=[]
class Failing:
 def connect(self,*args,**kwargs):attempts.append(1);started.set();raise OSError('fixture DB down')
class Clock:
 @staticmethod
 def sleep(seconds):stop.wait(.01)
ns={'running':True,'psycopg2':Failing(),'PG_DSN':'synthetic','verify_runtime_role':lambda c:None,'time':Clock}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
def run():
 try:ns['connect_db']()
 except RuntimeError:pass
worker=threading.Thread(target=run);worker.start();assert started.wait(1);worker.join(.05);blocked=worker.is_alive();ns['running']=False;stop.set();worker.join(1)
assert blocked
Path('/evidence/baseline-reproduction.json').write_text(json.dumps({'callback_connect_remains_blocked_after_error':blocked,'connection_attempts':len(attempts),'device_io':False},indent=2)+'\n')
