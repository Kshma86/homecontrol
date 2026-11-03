"""Run actual publisher/callback functions without starting hardware threads."""
import ast,json,unittest,os
from pathlib import Path
from types import SimpleNamespace
SOURCE=Path(os.environ.get('X10_TEST_SOURCE','/srv/docker/homecontrol/apps/xiaomi-x10/xiaomi_x10_bridge.py'))
class Client:
 def __init__(self):self.connected=False;self.attempts=[];self.retained={'test/bridge/online':'0'}
 def publish(self,topic,payload,retain=True):
  self.attempts.append((topic,payload))
  if self.connected and retain:self.retained[topic]=payload
 def subscribe(self,topic):pass
class OnlineTests(unittest.TestCase):
 def functions(self):
  tree=ast.parse(SOURCE.read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('publish','topic','on_connect')]
  client=Client();scope={'client':client,'CONFIG':{'base_topic':'test'},'last_state':{},'json':json,'time':SimpleNamespace(time=lambda:100),'command_dispatcher':None,'active_room_clean':None,'publish_room_clean_status':lambda *args:None}
  exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),scope)
  return scope,client
 def test_preconnection_attempt_cannot_suppress_online_after_connack(self):
  s,c=self.functions();s['publish']('bridge/online',1);self.assertEqual(c.retained['test/bridge/online'],'0')
  c.connected=True;s['on_connect'](c,None,None,0)
  self.assertEqual(c.retained['test/bridge/online'],'1');self.assertEqual(c.retained['test/bridge/status'],'online')
 def test_reconnect_replaces_lwt_despite_same_cache(self):
  s,c=self.functions();c.connected=True;s['on_connect'](c,None,None,0)
  c.retained['test/bridge/online']='0';s['on_connect'](c,None,None,0)
  self.assertEqual(c.retained['test/bridge/online'],'1')
 def test_refused_connection_never_announces_online(self):
  s,c=self.functions();s['on_connect'](c,None,None,5);self.assertEqual(c.attempts,[])
if __name__=='__main__':unittest.main(verbosity=2)
