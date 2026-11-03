"""HC-23 local worker observations. Probes read JSON, never touch hardware/MQTT."""
import argparse
import json
import math
import os
from pathlib import Path
import threading
import time

PATH = Path('/tmp/hc_worker_health.json')


def process_ticks(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def assess(status, *, now, ticks, mode='live', maximum=20):
    if mode not in ('live', 'ready') or not math.isfinite(maximum) or maximum <= 0:
        return False
    if not isinstance(status, dict) or status.get('process_ticks') != ticks:
        return False
    stamp = status.get('written_at')
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
        return False
    return (0 <= now - stamp <= maximum and status.get('live') is True
            and (mode == 'live' or status.get('ready') is True))


class WorkerHealth:
    def __init__(self, *, maximum=120, path=PATH, clock=time.monotonic):
        if not math.isfinite(maximum) or maximum <= 0:
            raise ValueError('worker health maximum must be positive and finite')
        self.maximum, self.path, self.clock = maximum, Path(path), clock
        self.pid, self.ticks = os.getpid(), process_ticks(os.getpid())
        self.created = clock()
        self.lock, self.stop_event = threading.Lock(), threading.Event()
        self.cycle = self.success_at = None
        self.thread = None

    def progress(self, *, success=False):
        with self.lock:
            self.cycle = self.clock()
            if success:
                self.success_at = self.cycle

    def snapshot(self, *, connected, commands=None, configured=True):
        now = self.clock()
        with self.lock:
            cycle, success = self.cycle, self.success_at
        # Startup grace permits slow discovery, but never reports readiness.
        live = now - (self.created if cycle is None else cycle) <= self.maximum
        if commands is not None:
            live = (live and commands.get('worker_alive') is True
                    and not commands.get('closed')
                    and commands.get('last_loop_age_sec', float('inf')) <= self.maximum)
        live = bool(live and not self.stop_event.is_set())
        return {'pid': self.pid, 'process_ticks': self.ticks, 'written_at': time.time(),
                'live': live, 'ready': bool(live and configured and connected and success is not None
                                          and now - success <= self.maximum),
                'mqtt_connected': bool(connected), 'configured': bool(configured),
                'last_cycle_age_sec': None if cycle is None else max(0, now-cycle),
                'last_success_age_sec': None if success is None else max(0, now-success)}

    def start(self, observations):
        if self.thread is not None:
            return
        def loop():
            while not self.stop_event.is_set():
                try:
                    payload = self.snapshot(**observations())
                    temporary = self.path.with_suffix('.tmp')
                    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'w') as handle:
                        json.dump(payload, handle)
                    temporary.replace(self.path)
                except Exception:
                    # A failed reporter becomes stale; it must not report healthy.
                    pass
                self.stop_event.wait(5)
        self.thread = threading.Thread(target=loop, name='worker-health', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)


def check(mode):
    try:
        if PATH.stat().st_size > 16384:
            return False
        status = json.loads(PATH.read_text())
        pid = status.get('pid')
        if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
            return False
        return assess(status, now=time.time(), ticks=process_ticks(pid), mode=mode)
    except (OSError, ValueError, TypeError, IndexError):
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('live', 'ready'), default='live')
    raise SystemExit(0 if check(parser.parse_args().mode) else 1)
