"""HC-11: one DB owner; MQTT admission never waits for database I/O.

Best effort QoS0: no offline replay. Overflow rejects the newest message;
expired queued messages and all queued messages at DB failure are discarded.
This inbox is distinct from the bounded HC-33 measurement batch.
"""
from collections import Counter, deque
from dataclasses import dataclass
import threading
import time


@dataclass(frozen=True)
class InboundMessage:
    topic: str
    payload: bytes
    retain: bool
    received_at: float
    received_monotonic: float

    @property
    def size(self):
        return len(self.payload) + len(self.topic.encode('utf-8'))


class MessageInbox:
    def __init__(self, max_messages=1000, max_bytes=8*1024*1024, max_age=5, *, clock=time.monotonic):
        if max_messages < 1 or max_bytes < 1 or not 0 < max_age < float('inf'):
            raise ValueError('Inbox limits must be positive and finite')
        self.max_messages, self.max_bytes, self.max_age = max_messages, max_bytes, max_age
        self.clock = clock
        self._items, self._bytes, self._closed = deque(), 0, False
        self._condition = threading.Condition()
        self._drops = Counter()
        self._accepted = self._processed = self._high_water = 0
        self._available = True

    def set_available(self, available):
        with self._condition:
            self._available = available
            if not available:
                self.discard('db_failure')

    def offer(self, message, *, ready):
        # Called by Paho: only a short in-memory critical section, never DB I/O.
        size = message.size
        with self._condition:
            reason = ('shutdown' if self._closed else 'db_unavailable' if not ready or not self._available else
                      'oversize' if size > self.max_bytes else
                      'overflow' if len(self._items) >= self.max_messages or self._bytes+size > self.max_bytes else None)
            if reason:
                self._drops[reason] += 1
                return False
            self._items.append(message)
            self._bytes += size
            self._accepted += 1
            self._high_water = max(self._high_water, len(self._items))
            self._condition.notify()
            return True

    def take(self, timeout=.1):
        with self._condition:
            if not self._items and not self._closed:
                self._condition.wait(timeout)
            while self._items:
                message = self._items.popleft()
                self._bytes -= message.size
                if self.clock()-message.received_monotonic > self.max_age:
                    self._drops['expired'] += 1
                    continue
                return message
            return None

    def processed(self):
        with self._condition:
            self._processed += 1

    def discard(self, reason):
        with self._condition:
            count = len(self._items)
            self._drops[reason] += count
            self._items.clear()
            self._bytes = 0
            self._condition.notify_all()
            return count

    def close(self):
        with self._condition:
            self._closed = True
            self.discard('shutdown')

    def status(self):
        with self._condition:
            return {'queued_messages': len(self._items), 'queued_bytes': self._bytes,
                    'max_messages': self.max_messages, 'max_bytes': self.max_bytes,
                    'max_age_seconds': self.max_age, 'accepted': self._accepted,
                    'processing_attempts': self._processed, 'high_water_messages': self._high_water,
                    'dropped': dict(self._drops), 'closed': self._closed}


class DatabaseWorker:
    def __init__(self, inbox, *, connect, process, tick, finish, close, retry_seconds=5,
                 stall_seconds=10, clock=time.monotonic):
        if not 0 < retry_seconds < float('inf') or not 0 < stall_seconds < float('inf'):
            raise ValueError('Worker intervals must be positive and finite')
        self.inbox, self.connect, self.process, self.tick = inbox, connect, process, tick
        self.finish, self.close = finish, close
        self.retry_seconds, self.stall_seconds, self.clock = retry_seconds, stall_seconds, clock
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._next_retry = 0
        self._active_since = self._last_cycle = None
        self._error = ''
        self._attempts = 0
        self._failed_messages = 0
        self._processing = False
        self.inbox.set_available(False)

    @property
    def ready(self):
        with self._lock:
            stalled = self._active_since is not None and self.clock()-self._active_since > self.stall_seconds
        return self._ready.is_set() and not stalled and not self._stop.is_set()

    def start(self):
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError('DB worker is stopping')
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name='ingest-db-writer', daemon=True)
                self._thread.start()
            return self._thread

    def invalidate(self, error):
        # Invoked only by the DB owner. Never reconnect/retry the failing message.
        self._ready.clear()
        self.inbox.set_available(False)
        if self._processing:
            self._failed_messages += 1
            self._processing = False
        try:
            self.close()
        finally:
            with self._lock:
                self._error = type(error).__name__
                self._next_retry = self.clock()+self.retry_seconds

    def _call(self, callback, *args):
        with self._lock:
            self._active_since = self.clock()
        try:
            return callback(*args)
        finally:
            with self._lock:
                self._active_since = None
                self._last_cycle = self.clock()

    def _run(self):
        try:
            while not self._stop.is_set():
                if not self._ready.is_set():
                    delay = self._next_retry-self.clock()
                    if delay > 0:
                        self._stop.wait(min(delay, .1))
                        continue
                    try:
                        with self._lock:
                            self._attempts += 1
                        self._call(self.connect)
                        if self._stop.is_set():
                            break
                        with self._lock:
                            self._error = ''
                        self._ready.set()
                        self.inbox.set_available(True)
                    except Exception as exc:
                        self.invalidate(exc)
                        continue
                message = self.inbox.take(.05)
                try:
                    if message is not None:
                        self._processing = True
                        self.inbox.processed()
                        self._call(self.process, message)
                        self._processing = False
                    if self._ready.is_set() and not self._stop.is_set():
                        self._call(self.tick)
                except Exception as exc:
                    self.invalidate(exc)
        finally:
            try:
                if self._ready.is_set():
                    self._call(self.finish)
            except Exception as exc:
                with self._lock:
                    self._error = type(exc).__name__
            finally:
                self._ready.clear()
                self.close()

    def stop(self, timeout=5):
        self._stop.set()
        self.inbox.close()
        if self._thread is not None:
            self._thread.join(max(0, timeout))
        return not (self._thread and self._thread.is_alive())

    def status(self):
        with self._lock:
            active, last = self._active_since, self._last_cycle
            state = {'running': bool(self._thread and self._thread.is_alive()),
                     'connect_attempts': self._attempts, 'last_error': self._error,
                     'db_failed_messages': self._failed_messages,
                     'stalled': active is not None and self.clock()-active > self.stall_seconds,
                     'last_cycle_age_sec': None if last is None else max(0,self.clock()-last),
                     'stopping': self._stop.is_set()}
        return {**state, 'db_ready': self.ready, 'inbox': self.inbox.status()}
