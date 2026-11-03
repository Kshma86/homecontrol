"""Shared, bounded robot transport and independent bridge progress monitoring."""
from contextlib import contextmanager
import fcntl
import math
import os
import re
import signal
import subprocess
import threading
import time


def positive_seconds(value):
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError('X10 time limits must be positive finite seconds')
    return float(value)


class MiioTransport:
    def __init__(self, executable, host, token, lock_file, command_timeout=20,
                 lock_timeout=30, *, runner=subprocess.run, clock=time.monotonic):
        self.executable, self.host, self.token = str(executable), host, token
        self.lock_file = str(lock_file)
        self.command_timeout = positive_seconds(command_timeout)
        self.lock_timeout = positive_seconds(lock_timeout)
        self.runner, self.clock = runner, clock
        self.thread_lock = threading.Lock()

    @contextmanager
    def locked(self):
        deadline = self.clock() + self.lock_timeout
        if not self.thread_lock.acquire(timeout=self.lock_timeout):
            raise RuntimeError('X10 MIIO lock wait timed out')
        fd = None
        try:
            fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        raise RuntimeError('X10 MIIO lock wait timed out') from None
                    time.sleep(min(0.05, remaining))
            yield
        finally:
            if fd is not None:
                os.close(fd)  # Releases the process lock on every failure too.
            self.thread_lock.release()

    def run(self, args, before_send=None):
        command = [self.executable, 'dreamevacuum', '--ip', self.host, '--token', self.token, *args]
        with self.locked():
            if before_send is not None:
                before_send()
            try:
                result = self.runner(command, text=True, capture_output=True, timeout=self.command_timeout)
            except subprocess.TimeoutExpired:
                # TimeoutExpired's default representation contains --token.
                raise RuntimeError('X10 MIIO command timed out') from None
            except OSError:
                raise RuntimeError('X10 MIIO process could not start') from None
            output, error = result.stdout.strip(), result.stderr.strip()
            combined = '\n'.join(part for part in (output, error) if part)
            if result.returncode != 0 or re.search(r'(^|\n)\s*(Error:|ERROR:)', combined):
                safe = combined.replace(self.token, '[redacted]') if self.token else combined
                raise RuntimeError(safe or 'X10 MIIO command failed')
            return output


_transport = None
_transport_guard = threading.Lock()


def run_miio(args, before_send=None):
    global _transport
    with _transport_guard:
        if _transport is None:
            import config
            _transport = MiioTransport(config.MIIOCLI, config.ROBOT_IP, config.ROBOT_TOKEN,
                                       config.MIIO_LOCK_FILE, config.MIIO_TIMEOUT_SEC,
                                       config.MIIO_LOCK_TIMEOUT_SEC)
    return _transport.run(args, before_send=before_send)


def run_map_refresh(command, timeout=120):
    """Kill the complete map subprocess group on timeout, including its MIIO child."""
    timeout = positive_seconds(timeout)
    process = subprocess.Popen(command, start_new_session=True)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        raise RuntimeError('X10 map refresh timed out') from None
    if code:
        raise RuntimeError(f'X10 map refresh failed with exit code {code}')


def valid_status_sample(state, battery):
    if isinstance(state, bool) or isinstance(battery, bool):
        return False
    try:
        state, battery = float(state), float(battery)
        return (math.isfinite(state) and state > 0 and state.is_integer()
                and math.isfinite(battery) and 0 <= battery <= 100)
    except (ValueError, TypeError, OverflowError):
        return False


class ProgressWatchdog:
    def __init__(self, timeout=300, *, clock=time.monotonic):
        self.timeout = positive_seconds(timeout)
        self.clock = clock
        self.lock = threading.Lock()
        now = clock()
        self.workers = {name: {'required': True, 'last_success': now}
                        for name in ('main', 'status')}

    def require(self, name, required):
        with self.lock:
            previous = self.workers.get(name)
            if previous is None or (required and not previous['required']):
                self.workers[name] = {'required': bool(required), 'last_success': self.clock()}
            else:
                previous['required'] = bool(required)

    def success(self, name):
        with self.lock:
            if name in self.workers:
                self.workers[name]['last_success'] = self.clock()

    def expired(self):
        with self.lock:
            now = self.clock()
            return {name: round(now - state['last_success'], 3)
                    for name, state in self.workers.items()
                    if state['required'] and now - state['last_success'] >= self.timeout}
