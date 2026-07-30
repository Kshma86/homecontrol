import json
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional

import paho.mqtt.client as mqtt


def compact_payload(payload: str):
    try:
        return json.loads(payload)
    except Exception:
        return payload


class TopicMonitorState:
    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        client_id: str,
        thread_name: str,
        subscriptions: Callable[[], Iterable[str]],
        relative_topic: Optional[Callable[[str], str]] = None,
        broker_meta: Optional[Dict[str, Any]] = None,
        max_raw_messages: int = 120,
        observe_topic: Optional[Callable[[str], Any]] = None,
    ):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client_id = client_id
        self.thread_name = thread_name
        self._subscriptions = subscriptions
        self.relative_topic = relative_topic
        self.broker_meta = broker_meta or {"host": mqtt_host, "port": mqtt_port}
        self.max_raw_messages = max_raw_messages
        self.observe_topic = observe_topic
        self.lock = threading.RLock()
        self.connected = False
        self.last_error = ""
        self.topic_state = {}
        self.raw_messages = []

    def start(self):
        thread = threading.Thread(target=self._loop, name=self.thread_name, daemon=True)
        thread.start()

    def subscriptions(self):
        result = []
        for topic in self._subscriptions():
            if topic not in result:
                result.append(topic)
        return result

    def _loop(self):
        while True:
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=self.client_id)
                client.on_connect = self._on_connect
                client.on_disconnect = self._on_disconnect
                client.on_message = self._on_message
                client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
                client.loop_forever()
            except Exception as exc:
                with self.lock:
                    self.connected = False
                    self.last_error = str(exc)
                time.sleep(5)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        with self.lock:
            self.connected = rc == 0
            self.last_error = "" if rc == 0 else f"MQTT connect rc={rc}"
        if rc == 0:
            for topic in self.subscriptions():
                client.subscribe(topic, qos=0)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        with self.lock:
            self.connected = False
            self.last_error = "" if rc == 0 else f"MQTT disconnected rc={rc}"

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        rel_topic = self.relative_topic(msg.topic) if self.relative_topic else msg.topic
        item = {
            "topic": msg.topic,
            "rel_topic": rel_topic,
            "payload": payload,
            "json": compact_payload(payload),
            "retain": bool(msg.retain),
            "timestamp": time.time(),
        }
        with self.lock:
            self.topic_state[rel_topic] = item
            self.raw_messages.insert(0, item)
            self.raw_messages = self.raw_messages[: self.max_raw_messages]
        if self.observe_topic:
            try:
                self.observe_topic(msg.topic)
            except Exception:
                pass

    def latest(self, rel_topic: str):
        item = self.topic_state.get(rel_topic)
        if not item:
            return None
        return {
            "topic": item["topic"],
            "rel_topic": item["rel_topic"],
            "payload": item["payload"],
            "json": item["json"],
            "retain": item["retain"],
            "timestamp": item["timestamp"],
            "age_sec": max(0, int(time.time() - item["timestamp"])),
        }

    def value(self, rel_topic: str, default=None):
        item = self.latest(rel_topic)
        if not item:
            return default
        return item["json"]

    def snapshot(self):
        with self.lock:
            topics = {name: self.latest(name) for name in self.topic_state}
            return {
                "mqtt_connected": self.connected,
                "last_error": self.last_error,
                "broker": self.broker_meta,
                "subscriptions": self.subscriptions(),
                "topics": topics,
                "raw": self._raw_messages(),
            }

    def _raw_messages(self):
        return [
            {
                "topic": item["topic"],
                "rel_topic": item["rel_topic"],
                "payload": item["payload"],
                "json": item["json"],
                "retain": item["retain"],
                "timestamp": item["timestamp"],
                "age_sec": max(0, int(time.time() - item["timestamp"])),
            }
            for item in self.raw_messages[:80]
        ]


class IrrigationMqttMonitorState(TopicMonitorState):
    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        device_id: str,
        topics: Dict[str, str],
        observe_topic: Optional[Callable[[str], Any]] = None,
    ):
        self.device_id = device_id
        self.named_topics = topics
        super().__init__(
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            client_id=f"hc-admin-{device_id}",
            thread_name="irrigation-mqtt-monitor",
            subscriptions=self._irrigation_subscriptions,
            relative_topic=lambda topic: topic,
            broker_meta={"host": mqtt_host, "port": mqtt_port},
            max_raw_messages=120,
            observe_topic=observe_topic,
        )

    def _irrigation_subscriptions(self):
        subs = list(self.named_topics.values())
        subs.extend(
            [
                f"homecontrol/tele/irrigation/{self.device_id}/#",
                f"homecontrol/stat/irrigation/{self.device_id}/#",
            ]
        )
        return subs

    def latest_for_topic(self, topic: str):
        return self.latest(topic)

    def snapshot(self):
        base = super().snapshot()
        base["topics"] = {name: self.latest_for_topic(topic) for name, topic in self.named_topics.items()}
        return base


class BaseTopicMonitorState(TopicMonitorState):
    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        base_topic: str,
        client_id: str,
        thread_name: str,
        max_raw_messages: int,
        observe_topic: Optional[Callable[[str], Any]] = None,
    ):
        self.base_topic = base_topic.rstrip("/")
        super().__init__(
            mqtt_host=mqtt_host,
            mqtt_port=mqtt_port,
            client_id=client_id,
            thread_name=thread_name,
            subscriptions=lambda: [f"{self.base_topic}/#"],
            relative_topic=lambda topic: topic.removeprefix(f"{self.base_topic}/"),
            broker_meta={"host": mqtt_host, "port": mqtt_port},
            max_raw_messages=max_raw_messages,
            observe_topic=observe_topic,
        )

    def snapshot(self):
        base = super().snapshot()
        base["base_topic"] = self.base_topic
        return base


class MqttClientService:
    def __init__(self, mqtt_host: str, mqtt_port: int, json_dumps: Callable[[Any], str]):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.json_dumps = json_dumps

    def check(self, timeout_s: float = 2.0) -> bool:
        ok = {"connected": False}

        def on_connect(client, userdata, flags, rc, properties=None):
            ok["connected"] = rc == 0
            client.disconnect()

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        client.on_connect = on_connect
        client.connect(self.mqtt_host, self.mqtt_port, keepalive=10)
        client.loop_start()

        t0 = time.time()
        while time.time() - t0 < timeout_s and not ok["connected"]:
            time.sleep(0.05)

        client.loop_stop()
        return ok["connected"]

    def publish(self, topic: str, payload: Any, qos: int = 0, retain: bool = False):
        if not topic:
            return False, "missing topic"
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        try:
            client.connect(self.mqtt_host, self.mqtt_port, keepalive=10)
            client.loop_start()
            if isinstance(payload, (dict, list)):
                payload_text = self.json_dumps(payload)
            else:
                payload_text = str(payload)
            result = client.publish(topic, payload_text, qos=qos, retain=retain)
            result.wait_for_publish(timeout=3)
            client.loop_stop()
            client.disconnect()
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                return False, f"publish failed rc={result.rc}"
            return True, "published"
        except Exception as exc:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass
            return False, str(exc)
