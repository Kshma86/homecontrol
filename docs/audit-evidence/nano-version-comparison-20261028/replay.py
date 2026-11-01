import importlib.util,json,types,sys
from pathlib import Path
sys.path.insert(0,'/app')
root=Path('/comparison')
observed=json.loads((root/'passive-mqtt.json').read_text())
result={}
for label in ('preaudit','r2','r4','live'):
 def load(name):
  spec=importlib.util.spec_from_file_location(label+'_'+name,root/label/(name+'.py'))
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 monitor=load('mqtt_monitor_service');contract=load('topic_contract')
 topics=contract.irrigation_topics('esp-irrigation-1')
 state=monitor.IrrigationMqttMonitorState('unused',1883,'esp-irrigation-1',topics)
 client=types.SimpleNamespace(subscribe=lambda *args,**kwargs:None)
 state._on_connect(client,None,None,0)
 for topic,info in observed['topics'].items():
  payload={k:None for k in info.get('keys',[])} if 'keys' in info else info.get('value')
  state._on_message(client,None,types.SimpleNamespace(topic=topic,payload=json.dumps(payload).encode(),retain=bool(info['retained_count'])))
 snap=state.snapshot()
 item={'subscriptions':state.subscriptions(),'observed_named_topics':[k for k,v in snap['topics'].items() if v is not None], 'observed_nano_status':snap['topics']['esp_nano_status'] is not None,'observed_tele':snap['topics']['pump_metrics'] is not None,'observed_named_config':snap['topics']['nano_config'] is not None}
 assert not item['observed_nano_status'] and not item['observed_tele'] and not item['observed_named_config']
 # Offline callback replay only: no MQTT client is connected or publishes.
 for name in ('esp_nano_status','pump_metrics'):
  state._on_message(client,None,types.SimpleNamespace(topic=topics[name],payload=b'{"online":true,"last_status_sec_ago":0,"last_tele_sec_ago":0,"valve":"CLOSED"}',retain=False))
 snap=state.snapshot();item['synthetic_status_accepted']=snap['topics']['esp_nano_status'] is not None;item['synthetic_tele_accepted']=snap['topics']['pump_metrics'] is not None
 assert item['synthetic_status_accepted'] and item['synthetic_tele_accepted']
 result[label]=item
assert len({json.dumps(x['subscriptions']) for x in result.values()})==1
print(json.dumps({'ok':True,'network_used':False,'versions':result},indent=2))
