"""Bounded process-local jobs and admission for the single control process."""
from concurrent.futures import Future
import fcntl
import os
import threading
import time


class Busy(RuntimeError):
    pass


class ProcessOwner:
    def __init__(self, path):
        self.path, self.fd, self.pid = path, None, None

    def acquire(self):
        if self.fd is not None and self.pid == os.getpid():
            return
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise RuntimeError('A backend control process already owns the workers') from None
        self.fd, self.pid = fd, os.getpid()

    def release(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class BoundedJobs:
    """No queue: timed-out jobs retain their slot until they actually finish."""
    def __init__(self, name, limit):
        self.name, self.limit = name, limit
        self._slots = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self._threads = set()
        self._closed = False

    def submit(self, callback, *args, **kwargs):
        with self._lock:
            if self._closed or not self._slots.acquire(blocking=False):
                raise Busy(self.name + ' capacity exhausted')
            future = Future()
            def run():
                try:
                    if future.set_running_or_notify_cancel():
                        try:
                            future.set_result(callback(*args, **kwargs))
                        except BaseException as exc:
                            future.set_exception(exc)
                finally:
                    with self._lock:
                        self._threads.discard(threading.current_thread())
                        self._slots.release()
            thread = threading.Thread(target=run, name=self.name, daemon=True)
            self._threads.add(thread)
            try:
                thread.start()
            except BaseException:
                self._threads.remove(thread)
                self._slots.release()
                raise
            return future

    def status(self):
        with self._lock:
            return {'name': self.name, 'active': len(self._threads), 'limit': self.limit, 'stopping': self._closed}

    def stop(self, timeout=0):
        deadline = time.monotonic() + max(0, timeout)
        with self._lock:
            self._closed = True
            threads = list(self._threads)
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        return not self.status()['active']


class RequestCapacity:
    # Eight HTTP threads: at most five long requests, three reserved for control.
    def __init__(self):
        self.limits = {'websocket': 2, 'ai': 1, 'backup': 1, 'diagnostic': 1}
        self._slots = {name: threading.BoundedSemaphore(n) for name, n in self.limits.items()}

    def category(self, path, upgrade=''):
        if upgrade.lower() == 'websocket':
            return 'websocket'
        if path.startswith('/api/ai/'):
            return 'ai'
        if path == '/api/backup' or path.startswith('/api/backup/') or path == '/api/context/backup':
            return 'backup'
        if path.startswith(('/api/performance', '/api/debug', '/api/context/performance')):
            return 'diagnostic'
        return None

    def acquire(self, category):
        return self._slots[category].acquire(blocking=False)

    def release(self, category):
        self._slots[category].release()
