import threading
import time
from typing import Callable, Iterable
from worker_runtime import ProcessOwner


def run_guarded_callbacks(label, callbacks):
    errors = []
    for name, callback in callbacks:
        try:
            callback()
        except Exception as exc:
            errors.append(name)
            print(f"[{label}] {name} error: {exc}", flush=True)
    return errors


class BootstrapService:
    def __init__(self, callbacks: Iterable[Callable[[], None]]):
        self.callbacks = list(callbacks)
        self._ready = False
        self._lock = threading.Lock()

    def ensure_all(self) -> None:
        for callback in self.callbacks:
            callback()

    def ensure_once(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            self.ensure_all()
            self._ready = True


class StartupService:
    def __init__(
        self,
        *,
        bootstrap: BootstrapService,
        scheduler_poll_seconds: int,
        weather_poll_seconds: int,
        power_wall_guard_seconds: int,
        safety_worker_enabled: bool,
        record_scheduler_shadow_audit: Callable[[], None],
        irrigation_scheduler_tick: Callable[[], None],
        x10_scheduler_tick: Callable[[], None],
        stop_overdue_sessions: Callable[[], None],
        fail_sessions_without_physical_watering: Callable[[], None],
        openweather_ready: Callable[[], bool],
        store_openweather_snapshot: Callable[[], dict],
        power_wall_guard_tick: Callable[[], None],
        power_wall_scheduler_tick: Callable[[], None],
        mqtt_monitor_start: Callable[[], None],
        x10_monitor_start: Callable[[], None],
        climate_monitor_start: Callable[[], None],
        mower_monitor_start: Callable[[], None] = lambda: None,
        combustion_safety_tick: Callable[[], None] = lambda: None,
        combustion_safety_poll_seconds: int = 1,
        context_refresh: Callable[[], None] = lambda: None,
        context_refresh_seconds: int = 4,
        context_refresh_enabled: bool = True,
        irrigation_scheduler_stop_tick: Callable[[], None] = lambda: None,
        irrigation_recovery_tick: Callable[[], None] = lambda: None,
        climate_scheduler_tick: Callable[[], None] = lambda: None,
        summary_refresh: Callable[[], None] = lambda: None,
        summary_poll_seconds: float = 5,
        owner_path=None,
        shutdown_resources: Callable[[float], None] = lambda timeout: None,
    ):
        self.bootstrap = bootstrap
        self.scheduler_poll_seconds = scheduler_poll_seconds
        self.weather_poll_seconds = weather_poll_seconds
        self.power_wall_guard_seconds = power_wall_guard_seconds
        self.safety_worker_enabled = safety_worker_enabled
        self.record_scheduler_shadow_audit = record_scheduler_shadow_audit
        self.irrigation_scheduler_tick = irrigation_scheduler_tick
        self.irrigation_scheduler_stop_tick = irrigation_scheduler_stop_tick
        self.irrigation_recovery_tick = irrigation_recovery_tick
        self.x10_scheduler_tick = x10_scheduler_tick
        self.climate_scheduler_tick = climate_scheduler_tick
        self.stop_overdue_sessions = stop_overdue_sessions
        self.fail_sessions_without_physical_watering = fail_sessions_without_physical_watering
        self.openweather_ready = openweather_ready
        self.store_openweather_snapshot = store_openweather_snapshot
        self.power_wall_guard_tick = power_wall_guard_tick
        self.power_wall_scheduler_tick = power_wall_scheduler_tick
        self.mqtt_monitor_start = mqtt_monitor_start
        self.x10_monitor_start = x10_monitor_start
        self.climate_monitor_start = climate_monitor_start
        self.mower_monitor_start = mower_monitor_start
        self.combustion_safety_tick = combustion_safety_tick
        self.combustion_safety_poll_seconds = combustion_safety_poll_seconds
        self.context_refresh = context_refresh
        self.context_refresh_seconds = context_refresh_seconds
        self.context_refresh_enabled = context_refresh_enabled
        self.summary_refresh = summary_refresh
        self.summary_poll_seconds = summary_poll_seconds
        self.shutdown_resources = shutdown_resources
        self._owner = ProcessOwner(owner_path) if owner_path else None
        self._stop = threading.Event()
        self._threads = {}
        self._monitors = {}
        self._progress = {}
        self._started = set()
        self._lock = threading.Lock()
        self._safety_ready = threading.Event()

    def start_application(self) -> None:
        self.ensure_started()

    def ensure_started(self) -> None:
        if self._stop.is_set():
            raise RuntimeError("Backend workers are stopping")
        if self._owner:
            with self._lock:
                if self._stop.is_set():
                    raise RuntimeError("Backend workers are stopping")
                self._owner.acquire()
        self.bootstrap.ensure_once()
        if self.safety_worker_enabled:
            self._start_once("irrigation-safety", self._safety_loop)
            self._start_once("scheduler", self._scheduler_loop)
        self._start_once("summary-refresh", self._summary_loop)
        self._start_once("openweather-poll", self._weather_loop)
        self._start_once("power-wall-guard", self._power_wall_loop)
        self._start_once("combustion-safety", self._combustion_safety_loop)
        self._start_monitor_once("mqtt-monitor", self.mqtt_monitor_start)
        self._start_monitor_once("x10-monitor", self.x10_monitor_start)
        self._start_monitor_once("climate-monitor", self.climate_monitor_start)
        self._start_monitor_once("mower-monitor", self.mower_monitor_start)
        if self.context_refresh_enabled:
            self._start_once("context-refresh", self._context_refresh_loop)

    def _start_once(self, name: str, target: Callable[[], None]) -> None:
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError("Backend workers are stopping")
            if name in self._started:
                return
            self._progress[name] = {"last_cycle_at": None, "last_success_at": None, "error": "", "active_since": None}
            def run():
                try:
                    target()
                except BaseException as exc:
                    with self._lock:
                        self._progress[name]["error"] = type(exc).__name__
            thread = threading.Thread(target=run, name=name, daemon=True)
            self._threads[name] = thread
            thread.start()
            self._started.add(name)

    def _start_monitor_once(self, name: str, start: Callable[[], None]) -> None:
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError("Backend workers are stopping")
            if name in self._started:
                return
            thread = start()
            self._monitors[name] = getattr(start, "__self__", None)
            if thread is not None:
                self._threads[name] = thread
            self._started.add(name)

    def _cycle(self, name, callback):
        now = time.monotonic()
        with self._lock:
            state = self._progress.setdefault(name, {})
            state['active_since'] = now
        error = ''
        try:
            errors = callback()
            if isinstance(errors, list) and errors:
                error = ', '.join(errors)
        except Exception as exc:
            error = type(exc).__name__
            print(f"[{name}] worker error: {exc}", flush=True)
        finally:
            with self._lock:
                state.update(last_cycle_at=time.monotonic(), active_since=None, error=error)
                if not error:
                    state['last_success_at'] = time.monotonic()

    def _power_wall_loop(self):
        def tick():
            return run_guarded_callbacks('POWER_WALL', (
                ('guard', self.power_wall_guard_tick), ('scheduler', self.power_wall_scheduler_tick)))
        while not self._stop.is_set():
            self._cycle('power-wall-guard', tick)
            self._stop.wait(max(2, self.power_wall_guard_seconds))

    def _safety_loop(self):
        while not self._stop.is_set():
            self._cycle('irrigation-safety', self._safety_tick)
            self._safety_ready.set()
            self._stop.wait(max(1, self.scheduler_poll_seconds))

    def _safety_tick(self) -> None:
        return run_guarded_callbacks("SAFETY", (
            ("irrigation session recovery", self.irrigation_recovery_tick),
            # Preserve the V2 effective-stop policy/reason before the generic
            # deadline fallback. Failure in either cannot skip the other.
            ("irrigation scheduled stop", self.irrigation_scheduler_stop_tick),
            ("stop overdue sessions", self.stop_overdue_sessions),
            ("no physical watering check", self.fail_sessions_without_physical_watering),
        ))

    def _scheduler_tick(self) -> None:
        return run_guarded_callbacks("SCHEDULER", (
            ("shadow audit", self.record_scheduler_shadow_audit),
            ("climate dispatch", self.climate_scheduler_tick),
            ("irrigation start", self.irrigation_scheduler_tick),
            ("xiaomi x10", self.x10_scheduler_tick),
        ))

    def _scheduler_loop(self):
        while not self._stop.is_set() and not self._safety_ready.wait(.1):
            pass
        while not self._stop.is_set():
            self._cycle('scheduler', self._scheduler_tick)
            self._stop.wait(max(1, self.scheduler_poll_seconds))

    def _weather_loop(self):
        def tick():
            if self.openweather_ready():
                self.store_openweather_snapshot()
        while not self._stop.is_set():
            self._cycle('openweather-poll', tick)
            self._stop.wait(max(60, self.weather_poll_seconds))

    def _combustion_safety_loop(self):
        while not self._stop.is_set():
            self._cycle('combustion-safety', self.combustion_safety_tick)
            self._stop.wait(max(.5, self.combustion_safety_poll_seconds))

    def _context_refresh_loop(self):
        while not self._stop.is_set():
            self._cycle('context-refresh', self.context_refresh)
            self._stop.wait(max(2, self.context_refresh_seconds))

    def _summary_loop(self):
        while not self._stop.is_set():
            self._cycle('summary-refresh', self.summary_refresh)
            self._stop.wait(max(1, self.summary_poll_seconds))

    def status(self):
        now = time.monotonic()
        intervals = {'scheduler': self.scheduler_poll_seconds, 'irrigation-safety': self.scheduler_poll_seconds,
                     'summary-refresh': self.summary_poll_seconds, 'openweather-poll': self.weather_poll_seconds,
                     'power-wall-guard': self.power_wall_guard_seconds,
                     'combustion-safety': self.combustion_safety_poll_seconds, 'context-refresh': self.context_refresh_seconds}
        workers = []
        with self._lock:
            for name, interval in intervals.items():
                state = dict(self._progress.get(name) or {})
                thread = self._threads.get(name)
                running = bool(thread and thread.is_alive())
                active = state.get('active_since')
                last = state.get('last_cycle_at')
                stalled = running and ((active is not None and now-active > 60)
                                      or (active is None and last is not None and now-last > max(10, interval*3)))
                workers.append({'name': name, 'key': name, 'enabled': name in self._started,
                                'running': running, 'stalled': bool(stalled),
                                'last_cycle_age_sec': None if last is None else max(0, now-last),
                                'last_success_age_sec': None if state.get('last_success_at') is None else max(0, now-state['last_success_at']),
                                'error': state.get('error', '')})
            monitors = list(self._monitors.items())
        for name, monitor in monitors:
            if monitor is not None and hasattr(monitor, 'worker_status'):
                workers.append(monitor.worker_status())
        return {'workers': workers, 'stopping': self._stop.is_set()}

    def stop(self, timeout=8):
        deadline = time.monotonic() + max(0, timeout)
        self._stop.set()
        self._safety_ready.set()
        with self._lock:
            monitors = list(self._monitors.values())
            threads = list(self._threads.values())
        for monitor in monitors:
            if monitor is not None and hasattr(monitor, 'stop'):
                monitor.stop(timeout=max(0, deadline-time.monotonic()))
        resources_stopped = self.shutdown_resources(max(0, deadline-time.monotonic())) is not False
        for thread in threads:
            thread.join(max(0, deadline-time.monotonic()))
        stopped = resources_stopped and all(not thread.is_alive() for thread in threads)
        # A stuck old controller keeps ownership until its process really exits.
        if stopped and self._owner:
            self._owner.release()
        return stopped
