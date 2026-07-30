import threading
import time
from typing import Callable, Iterable


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
        context_refresh: Callable[[], None] = lambda: None,
        context_refresh_seconds: int = 4,
        context_refresh_enabled: bool = True,
    ):
        self.bootstrap = bootstrap
        self.scheduler_poll_seconds = scheduler_poll_seconds
        self.weather_poll_seconds = weather_poll_seconds
        self.power_wall_guard_seconds = power_wall_guard_seconds
        self.safety_worker_enabled = safety_worker_enabled
        self.record_scheduler_shadow_audit = record_scheduler_shadow_audit
        self.irrigation_scheduler_tick = irrigation_scheduler_tick
        self.x10_scheduler_tick = x10_scheduler_tick
        self.stop_overdue_sessions = stop_overdue_sessions
        self.fail_sessions_without_physical_watering = fail_sessions_without_physical_watering
        self.openweather_ready = openweather_ready
        self.store_openweather_snapshot = store_openweather_snapshot
        self.power_wall_guard_tick = power_wall_guard_tick
        self.power_wall_scheduler_tick = power_wall_scheduler_tick
        self.mqtt_monitor_start = mqtt_monitor_start
        self.x10_monitor_start = x10_monitor_start
        self.climate_monitor_start = climate_monitor_start
        self.context_refresh = context_refresh
        self.context_refresh_seconds = context_refresh_seconds
        self.context_refresh_enabled = context_refresh_enabled
        self._started = set()
        self._lock = threading.Lock()

    def start_application(self) -> None:
        self.bootstrap.ensure_once()
        self.ensure_started()

    def ensure_started(self) -> None:
        self.bootstrap.ensure_once()
        if self.safety_worker_enabled:
            self._start_once("irrigation-safety", self._safety_loop)
        self._start_once("openweather-poll", self._weather_loop)
        self._start_once("power-wall-guard", self._power_wall_loop)
        self._start_monitor_once("mqtt-monitor", self.mqtt_monitor_start)
        self._start_monitor_once("x10-monitor", self.x10_monitor_start)
        self._start_monitor_once("climate-monitor", self.climate_monitor_start)
        if self.context_refresh_enabled:
            self._start_once("context-refresh", self._context_refresh_loop)

    def _start_once(self, name: str, target: Callable[[], None]) -> None:
        with self._lock:
            if name in self._started:
                return
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._started.add(name)

    def _start_monitor_once(self, name: str, start: Callable[[], None]) -> None:
        with self._lock:
            if name in self._started:
                return
            start()
            self._started.add(name)

    def _power_wall_loop(self) -> None:
        while True:
            try:
                self.power_wall_guard_tick()
                self.power_wall_scheduler_tick()
            except Exception as exc:
                print(f"[POWER_WALL] guard error: {exc}", flush=True)
            time.sleep(max(2, self.power_wall_guard_seconds))

    def _safety_loop(self) -> None:
        while True:
            try:
                try:
                    self.record_scheduler_shadow_audit()
                except Exception as exc:
                    print(f"[SCHEDULER] shadow audit error: {exc}", flush=True)
                self.irrigation_scheduler_tick()
                self.x10_scheduler_tick()
                self.stop_overdue_sessions()
                self.fail_sessions_without_physical_watering()
            except Exception as exc:
                print(f"[SAFETY] worker error: {exc}", flush=True)
            time.sleep(max(1, self.scheduler_poll_seconds))

    def _weather_loop(self) -> None:
        while True:
            try:
                if self.openweather_ready():
                    row = self.store_openweather_snapshot()
                    print(f"[WEATHER] stored openweathermap ts={row['ts'] if row else '-'}", flush=True)
            except Exception as exc:
                print(f"[WEATHER] worker error: {exc}", flush=True)
            time.sleep(max(60, self.weather_poll_seconds))

    def _context_refresh_loop(self) -> None:
        while True:
            try:
                self.context_refresh()
            except Exception as exc:
                print(f"[CONTEXT] refresh error: {exc}", flush=True)
            time.sleep(max(2, self.context_refresh_seconds))
