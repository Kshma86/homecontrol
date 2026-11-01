"""Runs only in the network-none test broker namespace. Synthetic payloads only."""
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch

import paho.mqtt.client as mqtt
from mqtt_credentials import configure_mqtt_auth
from mqtt_monitor_service import MqttClientService, TopicMonitorState
from mqtt_read_probe import read_one

ROOT=Path('/candidate')
TELE='homecontrol/tele/irrigation/esp-irrigation-1/pump_metrics'
CMD='homecontrol/cmd/irrigation/esp-irrigation-1/pump'
results=[]
active=[]

def env(role):
    return dict(MQTT_HOST='127.0.0.1',MQTT_PORT='1884',MQTT_USERNAME='hc_'+role,
        MQTT_PASSWORD_FILE=str(ROOT/'credentials'/(role+'.password')),MQTT_AUTH_REQUIRED='1')

def connect(role=None,port=1884,wrong=False):
    c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    event=threading.Event();status=[];messages=[]
    if role:
        with patch.dict(os.environ,env(role),clear=True):configure_mqtt_auth(c)
        if wrong:c.username_pw_set('hc_'+role,'not-the-password')
    c.on_connect=lambda client,user,flags,rc,properties=None:(status.append(rc),event.set())
    c.on_message=lambda client,user,msg:messages.append((msg.topic,msg.payload,bool(msg.retain)))
    c.connect('127.0.0.1',port,10);c.loop_start();active.append(c)
    assert event.wait(2),'no CONNACK'
    return c,status[0],messages

def wait_for(predicate):
    end=time.monotonic()+2
    while time.monotonic()<end:
        if predicate():return True
        time.sleep(.02)
    return False

def subscribe(c,topic):
    event=threading.Event()
    c.on_subscribe=lambda *a:event.set()
    c.subscribe(topic,qos=1)
    assert event.wait(2),'no SUBACK'

def publish(c,topic,value,retain=False):
    info=c.publish(topic,value,qos=1,retain=retain);info.wait_for_publish(2)
    assert info.is_published()

try:
    for role in ('backend','ingest','tuya','x10','x10_api','climate','growatt','grott','dashboard','zigbee2mqtt'):
        _,rc,_=connect(role);assert rc==0,role
    results.append('all_10_role_credentials_accepted')
    _,rc,_=connect();assert rc!=0
    _,rc,_=connect('backend',wrong=True);assert rc!=0
    results.append('anonymous_and_wrong_password_rejected_on_1884')
    backend,rc,received=connect('backend');subscribe(backend,'#')
    legacy,rc,legacy_received=connect(port=1883);assert rc==0;subscribe(legacy,'#')
    subscribe(legacy,'homecontrol/cmd/irrigation/esp-irrigation-1/#')
    publish(legacy,TELE,'fixture-telemetry',retain=True)
    assert wait_for(lambda:any(t==TELE and p==b'fixture-telemetry' for t,p,r in received))
    results.append('legacy_esp_telemetry_visible_to_authenticated_backend')
    with patch.dict(os.environ,env('backend'),clear=True):
        service=MqttClientService('127.0.0.1',1884,json.dumps)
        assert service.check()
        assert service.publish(CMD,{'cmd':'stop'})[0]
    assert wait_for(lambda:any(t==CMD and b'stop' in p for t,p,r in legacy_received))
    results.append('authenticated_backend_stop_reaches_legacy_esp')
    publish(legacy,'homecontrol/stat/irrigation/esp-irrigation-1/cmd_ack','fixture-ack')
    assert wait_for(lambda:any(p==b'fixture-ack' for t,p,r in received))
    results.append('legacy_ack_visible')
    for target in ('zigbee/fixture/set','homecontrol/xiaomi_x10/command/start',
                   'homecontrol/tele/irrigation/another-esp/pump_metrics',CMD):
        marker='forbidden-'+target
        publish(legacy,target,marker)
        time.sleep(.08)
        assert not any(p==marker.encode() for t,p,r in received),target
    results.append('legacy_foreign_topics_and_command_publish_denied')
    publish(backend,'zigbee/fixture/set','private-zigbee')
    time.sleep(.15)
    assert not any(p==b'private-zigbee' for t,p,r in legacy_received)
    results.append('legacy_cannot_read_other_domains')
    ingest,rc,ingest_received=connect('ingest');subscribe(ingest,TELE)
    assert wait_for(lambda:any(t==TELE and r for t,p,r in ingest_received))
    publish(ingest,CMD,'forbidden-ingest-command')
    time.sleep(.1);assert not any(p==b'forbidden-ingest-command' for t,p,r in received)
    results.append('ingest_retained_read_and_write_denial')
    # Positive allowed direction and cross-domain negative checks for bridges.
    for role,topic in [('tuya','homecontrol/tele/tuya/fixture/state'),('x10','homecontrol/xiaomi_x10/state'),
        ('climate','homecontrol/gree_climate/state'),('growatt','homecontrol/tele/growatt/cloud/state'),
        ('grott','homecontrol/tele/growatt/inverter/state'),('zigbee2mqtt','zigbee/bridge/state')]:
        client,rc,_=connect(role)
        marker='allowed-'+role;publish(client,topic,marker,retain=(role=='zigbee2mqtt'))
        assert wait_for(lambda:any(t==topic and p==marker.encode() for t,p,r in received)),role
        publish(client,CMD,'forbidden-'+role);time.sleep(.06)
        assert not any(p==('forbidden-'+role).encode() for t,p,r in received),role
    results.append('bridge_domain_writes_and_cross_domain_denials')
    # Command consumers keep their existing wildcard and retained/LWT behavior.
    tuya,rc,tuya_received=connect('tuya');subscribe(tuya,'homecontrol/cmd/tuya/+/switch')
    publish(backend,'homecontrol/cmd/tuya/fixture/switch','OFF')
    assert wait_for(lambda:any(p==b'OFF' for t,p,r in tuya_received))
    x10,rc,x10_received=connect('x10');subscribe(x10,'homecontrol/xiaomi_x10/command/#')
    publish(backend,'homecontrol/xiaomi_x10/command/stop','fixture-stop')
    assert wait_for(lambda:any(p==b'fixture-stop' for t,p,r in x10_received))
    climate,rc,climate_received=connect('climate');subscribe(climate,'homecontrol/gree_climate/command')
    publish(backend,'homecontrol/gree_climate/command','fixture-off')
    assert wait_for(lambda:any(p==b'fixture-off' for t,p,r in climate_received))
    results.append('tuya_x10_climate_commands_delivered')
    dashboard,rc,dashboard_received=connect('dashboard');subscribe(dashboard,'homecontrol/tele/irrigation/esp-irrigation-1/#')
    assert wait_for(lambda:any(t==TELE for t,p,r in dashboard_received))
    publish(dashboard,CMD,'dashboard-stop')
    assert wait_for(lambda:any(p==b'dashboard-stop' for t,p,r in legacy_received))
    publish(dashboard,'zigbee/fixture/set','forbidden-dashboard')
    time.sleep(.1);assert not any(p==b'forbidden-dashboard' for t,p,r in received)
    results.append('optional_dashboard_irrigation_scope_only')
    with patch.dict(os.environ,env('backend'),clear=True):
        monitor=TopicMonitorState('127.0.0.1',1884,'hc41-lab-monitor','hc41-monitor',lambda:[TELE])
        monitor.start()
        try:assert wait_for(lambda:monitor.latest(TELE) is not None)
        finally:assert monitor.stop()
        assert read_one('zigbee/bridge/state')=='allowed-zigbee2mqtt'
    results.append('real_backend_monitor_and_postboot_probe_authenticate')
    # Test actual broker LWT: close transport without a DISCONNECT.
    will=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    with patch.dict(os.environ,env('tuya'),clear=True):configure_mqtt_auth(will)
    will.will_set('homecontrol/tele/tuya/poller/availability','offline',qos=1,retain=True)
    ready=threading.Event();will.on_connect=lambda *a:ready.set()
    will.connect('127.0.0.1',1884,10);will.loop_start();assert ready.wait(2)
    will._sock_close();will.loop_stop()
    assert wait_for(lambda:any(t.endswith('/availability') and p==b'offline' for t,p,r in received))
    results.append('authenticated_lwt_published')
    legacy.disconnect();legacy.loop_stop()
    again,rc,_=connect(port=1883);assert rc==0
    publish(again,TELE,'fixture-after-reconnect')
    assert wait_for(lambda:any(p==b'fixture-after-reconnect' for t,p,r in received))
    results.append('legacy_reconnect_preserves_route')
finally:
    for c in active:
        c.disconnect();c.loop_stop()

Path('/evidence/broker-results.json').write_text(json.dumps(dict(passed=results,checks=len(results),
    production_messages=0,network='none; shared laboratory namespace',
    network_ip_filter_tested=False,physical_devices_tested=False),indent=2)+'\n')
print(json.dumps(dict(checks=len(results),passed=results)))
