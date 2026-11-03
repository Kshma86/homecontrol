"""HC-12 single command owner. Canonical source: apps/bridge_runtime.

The identical standalone file is copied into each bridge build context.
Only STOP/OFF is a cancellation barrier; ordinary commands are never coalesced.
"""
from collections import Counter, deque
from dataclasses import dataclass, field
import logging
import math
import os
import threading
import time


class CommandRejected(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass
class Command:
    target: str
    payload: object
    size: int
    expires_at: float
    priority: bool
    cancellable: bool
    owner: object = field(repr=False)
    cancelled: str = ''

    def check(self):
        """Recheck after acquiring an existing device/transport lock, before I/O."""
        with self.owner._condition:
            if self.cancelled:
                raise CommandRejected(self.cancelled)
            if self.owner._closed:
                raise CommandRejected('shutdown')
            if not self.owner._online:
                raise CommandRejected('connection_lost')
            if self.owner.clock() >= self.expires_at:
                raise CommandRejected('expired')


class CommandDispatcher:
    def __init__(self, handler, reject, *, name, capacity=32, max_age=30,
                 max_payload=4096, clock=time.monotonic):
        if isinstance(capacity, bool) or int(capacity) != capacity or capacity < 2:
            raise ValueError('command capacity must be an integer >= 2')
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('command max age must be positive and finite')
        if isinstance(max_payload, bool) or int(max_payload) != max_payload or max_payload < 1:
            raise ValueError('command max payload must be a positive integer')
        self.handler, self.reject, self.name = handler, reject, name
        self.capacity, self.max_age, self.max_payload = int(capacity), max_age, int(max_payload)
        self.clock = clock
        self._condition = threading.Condition()
        self._pending = deque()
        self._active = None
        self._thread = None
        self._closed = False
        self._online = False
        self._counts = Counter()
        self._last_loop = self.clock()

    @classmethod
    def configured(cls, handler, reject, *, name, prefix, default_max_age=30):
        return cls(handler, reject, name=name,
            capacity=int(os.getenv(prefix + '_COMMAND_QUEUE_SIZE', '32')),
            max_age=float(os.getenv(prefix + '_COMMAND_MAX_AGE_SEC', str(default_max_age))),
            max_payload=int(os.getenv(prefix + '_COMMAND_MAX_PAYLOAD_BYTES', '4096')))

    def start(self):
        with self._condition:
            if self._closed:
                raise ValueError('closed command dispatcher cannot restart')
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
                self._thread.start()
            return self._thread

    def _report(self, rejected):
        for item, code in rejected:
            with self._condition:
                self._counts[code] += 1
            try:
                self.reject(item, code)
            except Exception as exc:
                # Reporting is best effort, never a reason to replay an actuator call.
                logging.warning('Command rejection reporting failed (%s)', type(exc).__name__)

    def _expired(self):
        remaining = deque()
        rejected = []
        for item in self._pending:
            if self.clock() >= item.expires_at:
                rejected.append((item, 'expired'))
            else:
                remaining.append(item)
        self._pending = remaining
        return rejected

    def submit(self, target, payload, *, size, priority=False, cancellable=True, retained=False):
        item = Command(target, payload, size, self.clock() + self.max_age,
                       priority, cancellable, self)
        rejected = []
        with self._condition:
            rejected.extend(self._expired())
            code = ('retained' if retained else 'payload_too_large' if size > self.max_payload
                    else 'invalid_size' if size < 0 else 'shutdown' if self._closed
                    else 'offline' if not self._online else None)
            victims = [previous for previous in self._pending
                       if priority and previous.target == target and previous.cancellable]
            remaining = deque(previous for previous in self._pending
                              if not (priority and previous.target == target and previous.cancellable))
            if code is None:
                # One slot is reserved for STOP/OFF. Even STOPs obey the total bound.
                limit = self.capacity if priority else self.capacity - 1
                if len(remaining) >= limit:
                    code = 'queue_full'
            if code:
                rejected.append((item, code))
                accepted = False
            else:
                # Cancellation and admission are atomic: a rejected STOP changes no intent.
                self._pending = remaining
                rejected.extend((previous, 'superseded_by_stop') for previous in victims)
                if priority and self._active and self._active.target == target and self._active.cancellable:
                    self._active.cancelled = 'superseded_by_stop'
                self._pending.append(item)
                self._counts['accepted'] += 1
                self._condition.notify()
                accepted = True
        self._report(rejected)
        return accepted

    def set_online(self, online):
        """Every connection generation discards old commands; never replay on reconnect."""
        with self._condition:
            code = 'connection_reset' if online else 'connection_lost'
            rejected = [(item, code) for item in self._pending]
            self._pending.clear()
            if self._active:
                self._active.cancelled = code
            self._online = bool(online) and not self._closed
            self._condition.notify_all()
        self._report(rejected)

    def _run(self):
        while True:
            with self._condition:
                self._last_loop = self.clock()
                if self._closed:
                    return
                rejected = self._expired()
                if self._pending:
                    item = next((x for x in self._pending if x.priority), self._pending[0])
                    self._pending.remove(item)
                    self._active = item
                else:
                    item = None
                    if not rejected:
                        self._condition.wait(timeout=.25)
            self._report(rejected)
            if item is None:
                continue
            try:
                item.check()
                self.handler(item)
            except CommandRejected as exc:
                self._report([(item, exc.code)])
            except Exception:
                self._report([(item, 'execution_error')])
            finally:
                with self._condition:
                    self._active = None
                    self._counts['handled'] += 1
                    self._condition.notify_all()

    def snapshot(self):
        with self._condition:
            return dict(pending=len(self._pending), pending_bytes=sum(x.size for x in self._pending),
                in_flight=self._active is not None, online=self._online, closed=self._closed,
                worker_alive=self._thread is not None and self._thread.is_alive(),
                last_loop_age_sec=max(0, self.clock() - self._last_loop),
                counts=dict(self._counts))

    def close(self, timeout=2):
        with self._condition:
            self._closed = True
            self._online = False
            rejected = [(item, 'shutdown') for item in self._pending]
            self._pending.clear()
            if self._active:
                self._active.cancelled = 'shutdown'
            self._condition.notify_all()
            thread = self._thread
        self._report(rejected)
        if thread and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        return thread is None or not thread.is_alive()
