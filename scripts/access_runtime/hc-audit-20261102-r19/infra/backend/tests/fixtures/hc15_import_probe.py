"""Run in a fresh, isolated interpreter; importing app must do no external work."""
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock,patch

import psycopg


def forbidden(*args,**kwargs):
    raise AssertionError('HC-15: app import/wiring attempted external work')


def guard(event,args):
    if event in ('socket.connect','socket.connect_ex','socket.bind','subprocess.Popen','os.system','os.fork'):
        forbidden()
    if event=='open':
        path,mode,flags=args
        if isinstance(path,(str,bytes)):
            name=os.fsdecode(path)
            if name.startswith('/srv/docker/homecontrol/'):
                forbidden()
            if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
                forbidden()


sys.addaudithook(guard)
with patch.object(psycopg,'connect',side_effect=forbidden),patch.object(threading.Thread,'start',side_effect=forbidden):
    import app as module
    routes=sorted([{'rule':r.rule,'methods':sorted(r.methods),'endpoint':r.endpoint} for r in module.app.url_map.iter_rules()],key=lambda r:(r['rule'],r['endpoint']))
    require_lazy=all(getattr(module,n) is None for n in ('_startup_service','_scheduler_service','_irrigation_service','_climate_service'))
    if not require_lazy:raise AssertionError('App import initialized domain workers')
    calls=[]
    module.get_season_profile_service=lambda:SimpleNamespace(ensure_schema=lambda:calls.append('season'))
    module.ensure_scheduler_schema=lambda:calls.append('scheduler')
    module.fetch_all=lambda query,params=():calls.append(['climate',list(params)]) or [{'id':7}]
    module.fetch_one=lambda query,params=():calls.append(['session',list(params)]) or {'requested_stop_at':'fixture'}
    if module.fetch_climate_schedule_rules(' winter ')!=[{'id':7}]:raise AssertionError('Climate wiring changed result')
    if module.get_scheduler_service().fetch_irrigation_v2_session(42)!={'requested_stop_at':'fixture'}:raise AssertionError('Session wiring changed result')
    print(json.dumps({'routes':routes,'lazy_import':require_lazy,'calls':calls,'external_work':False}))
