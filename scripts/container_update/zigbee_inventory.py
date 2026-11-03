"""Bounded read-only MQTT inventory for the r23 activation continuation."""

PROBE_CODE=r'''
import json,os,re,threading,time
MAX_BYTES=2*1024**2
TOPICS=('zigbee/bridge/info','zigbee/bridge/devices')

def decode_topic(payload,topic):
    if topic not in TOPICS:raise ValueError('Unexpected inventory topic')
    if len(payload)>MAX_BYTES:raise ValueError('Inventory message exceeds bound')
    data=json.loads(payload)
    if topic==TOPICS[0]:
        if not isinstance(data,dict) or not isinstance(data.get('version'),str):
            raise ValueError('Invalid bridge information')
        return {'version':data['version'],'coordinator':data.get('coordinator')}
    if not isinstance(data,list) or not 2<=len(data)<=1024:
        raise ValueError('Incomplete device inventory')
    identities=[]
    for row in data:
        value=row.get('ieee_address') if isinstance(row,dict) else None
        if not isinstance(value,str) or re.fullmatch(r'0x[0-9a-fA-F]{16}',value) is None:
            raise ValueError('Invalid device identity')
        identities.append(value)
    if len(set(value.lower() for value in identities))!=len(identities):
        raise ValueError('Duplicate device identity')
    return sorted(identities)

def read_topic(topic):
    import paho.mqtt.client as mqtt
    from mqtt_credentials import configure_mqtt_auth
    done=threading.Event();values=[];errors=[]
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    configure_mqtt_auth(client)
    def connected(c,userdata,flags,rc,properties=None):
        if rc==0:c.subscribe(topic,qos=0)
        else:errors.append('MQTT authentication failed');done.set()
    def message(c,userdata,msg):
        try:values.append(decode_topic(msg.payload,topic))
        except (ValueError,UnicodeError,TypeError):errors.append('Invalid bounded MQTT inventory')
        done.set()
    client.on_connect=connected;client.on_message=message;client.connect_timeout=4
    deadline=time.monotonic()+5
    try:
        client.connect(os.getenv('MQTT_HOST','mqtt'),int(os.getenv('MQTT_PORT','1883')),keepalive=10)
        while not done.is_set() and time.monotonic()<deadline:
            client.loop(timeout=min(.1,max(.001,deadline-time.monotonic())))
        if errors or not values:raise ValueError('Bounded MQTT inventory unavailable')
        return values[0]
    finally:client.disconnect()

if __name__=='__main__':
    info=read_topic(TOPICS[0]);info['identities']=read_topic(TOPICS[1])
    print(json.dumps(info))
'''


def bridge(e,expected_version):
    raw=e.call(['docker','exec','homecontrol-backend','python','-B','-c',PROBE_CODE],timeout=20)
    import json
    result=json.loads(raw)
    if result.get('version')!=expected_version:raise ValueError('Zigbee bridge version differs')
    return result
