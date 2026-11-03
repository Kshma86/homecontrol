"""Bounded read-only MQTT probe for the staged post-boot adapter."""
import argparse
import os
import threading
import time
import paho.mqtt.client as mqtt
from mqtt_credentials import configure_mqtt_auth


def read_one(topic, timeout=4):
    if not topic or any(char in topic for char in ('#', '+', '\0')):
        raise ValueError('A single concrete topic is required')
    done = threading.Event()
    values = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    configure_mqtt_auth(client)
    def connected(c, userdata, flags, rc, properties=None):
        if rc == 0:c.subscribe(topic, qos=0)
        else:done.set()
    def message(c, userdata, msg):
        if len(msg.payload) <= 65536:
            values.append(msg.payload.decode('utf-8', errors='replace'))
        done.set()
    client.on_connect = connected
    client.on_message = message
    deadline = time.monotonic() + timeout
    client.connect_timeout = max(.1, timeout)
    try:
        client.connect(os.getenv('MQTT_HOST', 'mqtt'), int(os.getenv('MQTT_PORT', '1883')), keepalive=10)
        while not done.is_set() and time.monotonic() < deadline:
            client.loop(timeout=min(.1, max(.001, deadline-time.monotonic())))
        if not values:raise TimeoutError('MQTT read probe received no allowed message')
        return values[0]
    finally:
        client.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topic', required=True)
    args = parser.parse_args()
    print(read_one(args.topic))
