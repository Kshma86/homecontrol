"""Bounded change suppression at the MQTT client's local admission boundary.

QoS 0/1 admission is not a PUBACK or a physical observation. No payloads are
retained for replay: after reconnect the next poll supplies the latest values.
"""
import json
import math
import threading
import time
from collections import Counter


class ChangedPublisher:
    def __init__(self, *, heartbeat=60, rate=100, burst=100, capacity=8192,
                 clock=time.monotonic):
        if any(not math.isfinite(v) or v <= 0 for v in (heartbeat, rate, burst)):
            raise ValueError('publish timing/rate must be positive and finite')
        if isinstance(capacity, bool) or int(capacity) != capacity or capacity < 1:
            raise ValueError('publish cache capacity must be a positive integer')
        self.heartbeat, self.rate, self.burst, self.capacity = heartbeat, rate, burst, capacity
        self.clock = clock
        self.lock = threading.Lock()
        self.last = {}
        self.counts = Counter()
        self.online = False
        self.generation = 0
        self.tokens, self.updated = burst, clock()

    def connection(self, online):
        with self.lock:
            self.generation += 1
            self.online = bool(online)
            self.last.clear()
            # Repeated reconnects must not refill the bucket and defeat the bound.

    def publish(self, topic, payload, send, *, fingerprint=None):
        comparable = payload if fingerprint is None else fingerprint
        try:
            marker = json.dumps(comparable, ensure_ascii=False, sort_keys=True)
        except TypeError:
            marker = repr(comparable)
        now = self.clock()
        with self.lock:
            if not self.online:
                self.counts['offline'] += 1
                return False
            previous = self.last.get(topic)
            if previous and previous[0] == marker and now - previous[1] < self.heartbeat:
                self.counts['unchanged'] += 1
                return False
            self.tokens = min(self.burst, self.tokens + max(0, now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                self.counts['rate_limited'] += 1
                return False
            self.tokens -= 1
            generation = self.generation
        # Never hold our lock across paho calls/callbacks.
        try:
            accepted = send(topic, payload) is True
        except Exception:
            accepted = False
        with self.lock:
            if not accepted or not self.online or generation != self.generation:
                self.counts['not_admitted'] += 1
                return False
            if topic in self.last or len(self.last) < self.capacity:
                self.last[topic] = (marker, now)
            else:
                self.counts['cache_full'] += 1
            self.counts['client_admitted'] += 1
            return True

    def snapshot(self):
        with self.lock:
            return {'online': self.online, 'generation': self.generation,
                    'cached_topics': len(self.last), 'counts': dict(self.counts)}
