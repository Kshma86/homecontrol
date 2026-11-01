"""Reproduce the audit's two-consumer race from the immutable pre-repair source."""
import ast
import hashlib
import json
from pathlib import Path
from queue import Queue, Empty
import threading

BASE = Path('/srv/docker/homecontrol')
SOURCE = BASE/'scripts/access_runtime/hc-access-20261030-r10/apps/tuya-poller/tuya_poller.py'
EVIDENCE = BASE/'docs/audit-evidence/hc12-20261031'
before = json.loads((EVIDENCE/'before.json').read_text())
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before['source_sha256']['apps/tuya-poller/tuya_poller.py']
entered, release = threading.Event(), threading.Event()
class Finished(BaseException): pass
class FixtureQueue(Queue):
    def get(self, block=True, timeout=None):
        try:
            item = super().get(block=False)
        except Empty:
            if timeout is not None:
                raise Finished()
            raise
        if timeout is not None and item[1]['value']:
            entered.set()
            assert release.wait(2)
        return item

queue = FixtureQueue()
queue.put(('fixture', {'value': True}))
queue.put(('fixture', {'value': False}))
calls=[]
namespace=dict(command_queue=queue,Empty=Empty,
    handle_switch_command=lambda device,payload:calls.append(payload['value']))
nodes=[n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef)
       and n.name in {'drain_commands','command_worker'}]
assert len(nodes)==2
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<pre-repair Tuya>', 'exec'),namespace)
def worker():
    try: namespace['command_worker']()
    except Finished: pass
thread=threading.Thread(target=worker,daemon=True)
try:
    thread.start()
    assert entered.wait(2)
    namespace['drain_commands']()
finally:
    release.set()
    thread.join(2)
assert not thread.is_alive() and calls == [False,True]
report=dict(reproduced=True,pre_repair_executed_values=calls,expected_fifo_values=[True,False],
    source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),device_transport='fixture',physical_commands=False)
(EVIDENCE/'before-order.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
