"""Real broker/paho, actual Tuya callbacks/publisher, no device I/O."""
import ast
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt
sys.path.insert(0,'/work/apps/tuya-poller')
from telemetry_publish import ChangedPublisher

def until(predicate):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.01)
    raise AssertionError('broker fixture timed out')

received=[]
subscribed=threading.Event()
observer=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1,client_id='hc32-observer')
observer.on_connect=lambda c,*args:c.subscribe('fixture/#',qos=1)
observer.on_subscribe=lambda *args:subscribed.set()
observer.on_message=lambda c,u,m:received.append((m.topic,json.loads(m.payload)))
for attempt in range(30):
    try:
        observer.connect('hc32-23-43-20261031-broker',1883,10)
        break
    except OSError:time.sleep(.1)
else:raise RuntimeError('lab broker not ready')
observer.loop_start()
assert subscribed.wait(5)

now=[0.0]
cache=ChangedPublisher(heartbeat=.1,rate=20,burst=20,clock=lambda:now[0])
sender=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1,client_id='hc32-sender')
ns=dict(Any=Any,json=json,telemetry_publisher=cache,SINK_MQTT=True,mqtt=mqtt,
        mqtt_client=sender,mqtt_connected=False,MQTT_QOS=0,MQTT_COMMAND_TOPIC='commands',
        command_dispatcher=None,publish_poller_info=lambda:None)
names={'mqtt_publish','mqtt_publish_changed','mqtt_on_connect','mqtt_on_disconnect','_mqtt_topic_join'}
tree=ast.parse(Path('/work/apps/tuya-poller/tuya_poller.py').read_text())
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
assert len(nodes)==len(names)
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual Tuya publisher>','exec'),ns)
sender.on_connect=ns['mqtt_on_connect']
sender.on_disconnect=ns['mqtt_on_disconnect']
sender.connect('hc32-23-43-20261031-broker',1883,10)
sender.loop_start()
report=[]
try:
    until(lambda:ns['mqtt_connected'])
    send=lambda value,**kw:ns['mqtt_publish_changed']('fixture/state',{'value':value},**kw)
    assert send(1)
    until(lambda:('fixture/state',{'value':1}) in received)
    report.append('qos0_local_admission_and_broker_observation')
    assert not send(1)
    report.append('unchanged_suppressed')
    sender.disconnect()
    until(lambda:not ns['mqtt_connected'])
    sender.loop_stop()
    assert not send(2)
    assert not cache.last
    report.append('offline_keeps_value_publishable')
    sender.reconnect()
    sender.loop_start()
    until(lambda:ns['mqtt_connected'])
    assert send(3,qos=1)
    until(lambda:('fixture/state',{'value':3}) in received)
    assert ('fixture/state',{'value':2}) not in received
    report.append('reconnect_uses_next_poll_latest_value_without_payload_replay')
    accepted=sum(cache.publish('fixture/burst/'+str(i),{'value':i},
        lambda topic,payload:ns['mqtt_publish'](topic,payload)) for i in range(2000))
    assert accepted<=18
    report.append('burst_2000_bounded_by_remaining_18_tokens')
    now[0]=1
    assert send(3)
    report.append('heartbeat_republishes_unchanged_state')
    print('HC32_BROKER_RESULT='+json.dumps({'passed':len(report),'cases':report,
        'burst_client_admitted':accepted,'hardware_contacted':False,'clock':'controlled token-bucket clock',
        'success_boundary':'local_client_admission; separate broker observations above'}))
finally:
    sender.disconnect();sender.loop_stop()
    observer.disconnect();observer.loop_stop()
