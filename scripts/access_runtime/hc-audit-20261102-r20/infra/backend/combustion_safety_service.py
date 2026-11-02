import math
from copy import deepcopy
import threading
import time
from typing import Any, Callable, Dict

from combustion_state_store import CombustionStateStore


LEVELS = {"idle", "green", "secondary", "closed", "co_warning", "danger", "latched", "disabled", "unknown"}


class SafetyCommand:
    """One target's bounded, monotonic retry episode; publish is not observation."""
    def __init__(self, entity_id, topic, payload, max_attempts, retry_seconds):
        self.entity_id, self.topic, self.payload = entity_id, topic, payload
        self.max_attempts, self.retry_seconds = max_attempts, retry_seconds
        self.attempts = 0
        self.next_attempt = 0.0
        self.first_attempt_at = None
        self.observed_at = None
        self.published = False
        self.last_publish_ok = None
        self.message = ''

    def attempt(self, publish):
        now = time.monotonic()
        if self.observed_at is not None or self.attempts >= self.max_attempts or now < self.next_attempt:
            return None
        self.attempts += 1
        self.next_attempt = now + self.retry_seconds
        if self.first_attempt_at is None:
            self.first_attempt_at = time.time()
        try:
            ok, message = publish(self.topic, self.payload)
        except Exception as exc:
            ok, message = False, str(exc)
        self.last_publish_ok = bool(ok)
        self.published = self.published or bool(ok)
        self.message = str(message)
        return bool(ok)

    def status(self):
        observed = self.observed_at is not None
        exhausted = self.attempts >= self.max_attempts and not observed
        return dict(entity_id=self.entity_id, topic=self.topic, desired=self.payload,
                    attempts=self.attempts, max_attempts=self.max_attempts,
                    published=self.published, last_publish_ok=self.last_publish_ok,
                    observed=observed, observed_at_epoch=self.observed_at,
                    message=self.message, requires_attention=exhausted,
                    next_retry_in_seconds=None if exhausted or observed else max(0, self.next_attempt-time.monotonic()))


class CombustionSafetyService:
    """Supplementary extractor/combustion guard; certified alarms remain authoritative."""

    def __init__(self, fetch_all: Callable[..., Any], fetch_one: Callable[..., Any], execute_one: Callable[..., Any],
                 publish_mqtt: Callable[..., Any], binding_entity_id: Callable[[str], Any],
                 zigbee_radio_status: Callable[[str], Dict[str, Any]] = lambda ext_id: {},
                 command_retry_seconds: float = 10, command_max_attempts: int = 3,
                 observation_max_age_seconds: float = 60, runtime_store=None,
                 input_max_age_seconds: float = 300, snapshot_max_age_seconds: float = 5):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.publish_mqtt = publish_mqtt
        self.binding_entity_id = binding_entity_id
        self.zigbee_radio_status = zigbee_radio_status
        self.fan_active = False
        self.fan_candidate_since = None
        self.last_level = None
        self.last_co = None
        self.co_warning_active = False
        self.last_signal_at = 0.0
        self.pulse_off_at = 0.0
        self.indicator_on = False
        self.shutdown_sent = False
        self.latched = True  # Unknown until the worker restores the durable row.
        self.preview_generation = 0
        self.preview_lock = threading.Lock()
        if any(not math.isfinite(float(v)) or float(v) <= 0 for v in (command_retry_seconds, observation_max_age_seconds)):
            raise ValueError('combustion retry/observation limits must be finite and positive')
        if type(command_max_attempts) is not int or not 1 <= command_max_attempts <= 100:
            raise ValueError('combustion command_max_attempts must be an integer in 1..100')
        self.command_retry_seconds = float(command_retry_seconds)
        self.command_max_attempts = command_max_attempts
        self.observation_max_age_seconds = float(observation_max_age_seconds)
        self.command_lock = threading.RLock()
        self.shutdown_command = None
        self.indicator_command = None
        if any(not math.isfinite(float(v)) or float(v) <= 0 for v in (input_max_age_seconds, snapshot_max_age_seconds)):
            raise ValueError('combustion input/snapshot ages must be finite and positive')
        self.input_max_age_seconds = float(input_max_age_seconds)
        self.snapshot_max_age_seconds = float(snapshot_max_age_seconds)
        self.runtime_store = runtime_store if runtime_store is not None else CombustionStateStore(fetch_one, execute_one)
        self._decision_lock = threading.RLock()
        self._snapshot_lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._runtime_loaded = False
        self._runtime_revision = None
        self._persisted_state = None
        self._pending_latch = False
        self.last_co_sample_at = None
        self._evaluated_monotonic = None
        self._snapshot = {"ok": False, "level": "latched", "would_level": "latched",
                          "reason": "runtime state not restored; awaiting worker", "latched": True,
                          "fan_active": None, "danger": None, "events": [],
                          "persistence": {"restored": False, "error": "not restored"}}

    @property
    def last_snapshot(self):
        return self.state_payload()

    @staticmethod
    def _value(row):
        if not row:
            return None
        for key in ("v_bool", "v_num", "v_text", "v_json"):
            if row.get(key) is not None:
                return row[key]
        return None

    @staticmethod
    def _truthy(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value or "").strip().lower() in {"1", "true", "on", "yes", "alarm", "detected", "smoke", "fire"}

    @staticmethod
    def _hex_to_xy(value: str):
        text = str(value or "").strip()
        if len(text) != 7 or not text.startswith("#"):
            raise ValueError("indicator colors must use #RRGGBB format")
        try:
            red, green, blue = (int(text[index:index + 2], 16) / 255 for index in (1, 3, 5))
        except ValueError as exc:
            raise ValueError("indicator colors must use #RRGGBB format") from exc
        linear = lambda channel: channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        red, green, blue = linear(red), linear(green), linear(blue)
        x_value = red * 0.664511 + green * 0.154324 + blue * 0.162028
        y_value = red * 0.283881 + green * 0.668433 + blue * 0.047685
        z_value = red * 0.000088 + green * 0.072310 + blue * 0.986039
        total = x_value + y_value + z_value
        return {"x": round(x_value / total, 4), "y": round(y_value / total, 4)} if total else {"x": 0.0, "y": 0.0}

    def _state(self, entity_id, keys):
        if not entity_id:
            return {}
        rows = self.fetch_all(
            "select key,ts,v_num,v_bool,v_text,v_json,meta from hc.entity_state where entity_id=%s and key=any(%s)",
            (entity_id, list(keys)),
        )
        return {row["key"]: {"value": self._value(row), "ts": row.get("ts"), "meta": row.get("meta")} for row in rows}

    def config(self):
        return self.fetch_one("select * from hc.combustion_safety_config where singleton=true") or {"enabled": False}

    @staticmethod
    def _epoch(value):
        try:
            return value.timestamp() if hasattr(value, 'timestamp') else float(value)
        except (ValueError, TypeError, AttributeError):
            return None

    def _fresh(self, sample, now):
        # Continuous power/actuation feedback still has an age limit.
        # A sample can arrive while this evaluation is reading the DB. Compare
        # against the read/check time, not the earlier tick-start timestamp.
        now = time.time()
        stamp = self._epoch(sample.get('ts'))
        meta = sample.get('meta') or {}
        return (stamp is not None and math.isfinite(stamp) and 0 <= now-stamp <= self.input_max_age_seconds
                and isinstance(meta, dict) and meta.get('retained') is False)

    def _recorded_event(self, sample):
        # Sleeping CO/smoke/contact devices report changes, not periodic measurements.
        # Radio presence is checked separately; it never manufactures a clear
        # state or a newer event timestamp. Retained/unknown/future data cannot
        # authorize acknowledgement even while the radio is present.
        stamp = self._epoch(sample.get('ts'))
        meta = sample.get('meta') or {}
        return (stamp is not None and math.isfinite(stamp) and stamp <= time.time()
                and isinstance(meta, dict) and meta.get('retained') is False)

    @staticmethod
    def _alarm_known(value):
        return (type(value) is bool or (type(value) in (int, float) and math.isfinite(value))
                or str(value).strip().lower() in {'true', 'false', 'on', 'off', '1', '0', 'clear', 'alarm', 'detected', 'smoke', 'fire'})

    def _radio_for(self, entity_id):
        row = self.fetch_one("select d.ext_id from hc.entity e join hc.device d on d.id=e.device_id where e.id=%s", (entity_id,)) if entity_id else None
        return self.zigbee_radio_status(row['ext_id']) if row else {}

    def _clear_inputs(self, ids, co_state, smoke_state, co_radio, now, smoke_radio=None):
        co_sources = {k: v for k, v in co_state.items() if k != 'fault'}
        co_known = bool(ids.get('combustion_co_sensor') and co_sources and co_radio.get('radio_online') is True)
        for key, sample in co_sources.items():
            value = sample.get('value')
            numeric = type(value) in (int, float) and math.isfinite(value) and value >= 0
            co_known = co_known and self._recorded_event(sample) and (self._alarm_known(value) if key == 'carbon_monoxide' else numeric)
        fault = self._truthy((co_state.get('fault') or {}).get('value'))
        if 'fault' in co_state:
            co_known = co_known and self._recorded_event(co_state['fault']) and self._alarm_known(co_state['fault'].get('value'))
        smoke_known = not ids.get('combustion_smoke_sensor') or bool(smoke_state) and (smoke_radio or {}).get('radio_online') is True and all(
            self._recorded_event(sample) and self._alarm_known(sample.get('value')) for sample in smoke_state.values())
        return {'co': bool(co_known and not fault), 'smoke': bool(smoke_known), 'fault': fault}

    def _runtime_state(self):
        return dict(latched=self.latched, co_warning_active=self.co_warning_active,
                    last_co=self.last_co, last_co_sample_at=self.last_co_sample_at)

    def _restore_runtime(self):
        if self._runtime_loaded:
            return
        row = self.runtime_store.load()
        self.latched = bool(row['latched']) or self._pending_latch
        self.co_warning_active = bool(row['co_warning_active']) or self.co_warning_active
        self.last_co = row['last_co']
        self.last_co_sample_at = self._epoch(row['last_co_sample_at'])
        self._runtime_revision = row['revision']
        self._persisted_state = dict(latched=bool(row['latched']), co_warning_active=bool(row['co_warning_active']),
                                    last_co=row['last_co'], last_co_sample_at=self.last_co_sample_at)
        self._runtime_loaded = True

    def _save_runtime(self, *, acknowledge=False):
        if not self._runtime_loaded:
            raise RuntimeError('runtime state not restored')
        state = self._runtime_state()
        if state != self._persisted_state or acknowledge:
            row = self.runtime_store.save(self._runtime_revision, state, acknowledge=acknowledge)
            self._runtime_revision = row['revision']
            self._persisted_state = state
        self._pending_latch = False

    @staticmethod
    def _set_level(snapshot):
        if snapshot['latched']:
            level, reason = ('danger' if snapshot['danger'] else 'latched'), 'alarm latched'
        elif snapshot['co_warning_active']:
            level, reason = 'co_warning', 'CO rising or above warning threshold'
        elif not all(snapshot['input_health'].get(k) for k in ('fan', 'co', 'smoke')):
            level, reason = 'unknown', 'missing, stale, offline or invalid safety input'
        elif not snapshot['fan_active']:
            level, reason = 'idle', 'extractor below threshold'
        elif snapshot['primary_open']:
            level, reason = 'green', 'primary combustion-air opening is open'
        elif snapshot['secondary_open']:
            level, reason = 'secondary', 'secondary combustion-air opening is open'
        else:
            level, reason = 'closed', 'all configured combustion-air openings are closed or unknown'
        snapshot.update(would_level=level, would_reason=reason)
        if snapshot['config'].get('enabled'):
            snapshot.update(level=level, reason=reason)
        else:
            snapshot.update(level='disabled', reason='guard disabled')

    def _update_fan(self, power, config, now):
        desired = self.fan_active
        if power is not None:
            if self.fan_active and power <= float(config["fan_off_w"]):
                desired = False
            elif not self.fan_active and power >= float(config["fan_on_w"]):
                desired = True
            else:
                self.fan_candidate_since = None
                return
        if desired == self.fan_active:
            self.fan_candidate_since = None
            return
        if self.fan_candidate_since is None:
            self.fan_candidate_since = now
            return
        delay = int(config["fan_on_seconds"] if desired else config["fan_off_seconds"])
        if now - self.fan_candidate_since >= delay:
            self.fan_active = desired
            self.fan_candidate_since = None

    def _evaluate(self, now):
        config = self.config()
        ids = {key: self.binding_entity_id(key) for key in (
            "combustion_extractor", "combustion_indicator", "combustion_co_sensor", "combustion_smoke_sensor"
        )}
        fan_state = self._state(ids["combustion_extractor"], ("power", "power_w"))
        power = next((fan_state[k]["value"] for k in ("power", "power_w") if k in fan_state), None)
        power = float(power) if power is not None else None
        power_sample = next((fan_state[k] for k in ('power', 'power_w') if k in fan_state), {})
        fan_fresh = type(power_sample.get('value')) in (int, float) and math.isfinite(power) and power >= 0 and self._fresh(power_sample, now)
        if fan_fresh:
            self._update_fan(power, config, time.monotonic())
        else:
            self.fan_candidate_since = None

        openings = self.fetch_all(
            """
            select e.id entity_id,e.name,d.location,d.ext_id,osp.extractor_air_role,s.v_bool contact,s.ts,s.meta
            from hc.opening_sensor_policy osp join hc.entity e on e.id=osp.entity_id
            join hc.device d on d.id=e.device_id left join hc.entity_state s on s.entity_id=e.id and s.key='contact'
            where osp.extractor_air_role in ('primary','secondary') and e.is_active=true and d.is_active=true
            order by osp.extractor_air_role,e.id
            """
        )
        openings = [{**x, **self.zigbee_radio_status(x.get("ext_id"))} for x in openings]
        # Contact is an event, not a periodic measurement. A known live opening
        # remains open while radio presence is confirmed; do not invent a new
        # contact timestamp from that presence or from evaluating the guard.
        primary_open = any(x.get("extractor_air_role") == "primary" and x.get("contact") is False and x.get("radio_online") is True and self._recorded_event(x) for x in openings)
        secondary_open = any(x.get("extractor_air_role") == "secondary" and x.get("contact") is False and x.get("radio_online") is True and self._recorded_event(x) for x in openings)

        co_state = self._state(ids["combustion_co_sensor"], ("carbon_monoxide", "carbon_monoxide_value", "co", "co_ppm", "fault"))
        co_entity = self.fetch_one("select d.ext_id from hc.entity e join hc.device d on d.id=e.device_id where e.id=%s", (ids["combustion_co_sensor"],)) if ids["combustion_co_sensor"] else None
        co_radio = self.zigbee_radio_status(co_entity.get("ext_id")) if co_entity else {}
        indicator_entity = self.fetch_one("select d.ext_id from hc.entity e join hc.device d on d.id=e.device_id where e.id=%s", (ids["combustion_indicator"],)) if ids["combustion_indicator"] else None
        indicator_radio = self.zigbee_radio_status(indicator_entity.get("ext_id")) if indicator_entity else {}
        co_alarm = self._truthy((co_state.get("carbon_monoxide") or {}).get("value"))
        co_value = next(((co_state.get(k) or {}).get("value") for k in ("carbon_monoxide_value", "co_ppm", "co") if (co_state.get(k) or {}).get("value") is not None), None)
        co_value = float(co_value) if co_value is not None else None
        co_sample = next((co_state[k] for k in ('carbon_monoxide_value', 'co_ppm', 'co') if k in co_state), {})
        co_stamp = self._epoch(co_sample.get('ts'))
        co_new = (type(co_sample.get('value')) in (int, float) and co_value is not None and math.isfinite(co_value) and co_value >= 0 and self._recorded_event(co_sample)
                  and (self.last_co_sample_at is None or co_stamp > self.last_co_sample_at))
        co_rising = bool(co_new and self.last_co is not None and co_value-self.last_co >= float(config.get('co_rise_ppm', 2)))
        if co_new:
            self.last_co, self.last_co_sample_at = co_value, co_stamp

        smoke_state = self._state(ids["combustion_smoke_sensor"], ("smoke", "smoke_alarm", "fire", "alarm"))
        smoke_alarm = any(self._truthy(x.get("value")) for x in smoke_state.values())
        smoke_radio = self._radio_for(ids['combustion_smoke_sensor'])
        health = self._clear_inputs(ids, co_state, smoke_state, co_radio, now, smoke_radio)
        health['fan'] = bool(fan_fresh)
        danger = co_alarm or smoke_alarm or (co_value is not None and co_value >= float(config.get("co_shutdown_ppm", 20)))
        warning = co_rising or (co_value is not None and co_value >= float(config.get("co_warning_ppm", 10)))
        if warning:
            self.co_warning_active = True
        elif not self.fan_active and fan_fresh and power <= float(config['fan_off_w']) and health['co'] and co_value is not None and co_value <= 0:
            self.co_warning_active = False
        if danger:
            self.latched = True
            self._pending_latch = True

        result = {"ok": True, "fan_active": self.fan_active, "input_health": health,
                "power_w": power, "primary_open": primary_open, "secondary_open": secondary_open,
                "openings": openings, "co": {"value_ppm": co_value, "alarm": co_alarm, "rising": co_rising, "state": co_state, **co_radio},
                "indicator": {"configured": bool(ids["combustion_indicator"]), **indicator_radio},
                "smoke": {"configured": bool(ids["combustion_smoke_sensor"]), "alarm": smoke_alarm, "state": smoke_state, **smoke_radio},
                "danger": danger, "co_warning_active": self.co_warning_active, "latched": self.latched, "bindings": ids, "config": config,
                "actuation": self._actuation_payload(),
                "signal": {"indicator_on": self.indicator_on, "last_signal_at_epoch": self.last_signal_at,
                           "pulse_off_at_epoch": self.pulse_off_at}}

        self._set_level(result)
        return result

    def evaluate(self, now=None):
        # Compatibility read adapter: only tick may advance the decision state.
        return self.state_payload()

    def _new_command(self, entity_id, topic, payload):
        return SafetyCommand(entity_id, topic, payload, self.command_max_attempts, self.command_retry_seconds)

    def _matching_observation(self, command, expected, after=None):
        if command.first_attempt_at is None:
            return None
        state = self._state(command.entity_id, expected)
        stamps = []
        for key, matches in expected.items():
            sample = state.get(key) or {}
            meta = sample.get("meta") or {}
            stamp = sample.get("ts")
            try:
                stamp = stamp.timestamp() if hasattr(stamp, 'timestamp') else float(stamp)
                if (not math.isfinite(stamp) or not 0 <= time.time()-stamp <= self.observation_max_age_seconds
                        or stamp <= max(command.first_attempt_at, after or 0)
                        or not isinstance(meta, dict) or meta.get('retained') is not False
                        or not matches(sample.get('value'))):
                    return None
            except (ValueError, TypeError, AttributeError):
                return None
            stamps.append(stamp)
        return min(stamps) if stamps else None

    def _actuation_payload(self):
        with self.command_lock:
            return {"shutdown": self.shutdown_command.status() if self.shutdown_command else None,
                    "indicator": self.indicator_command.status() if self.indicator_command else None}

    def _publish_indicator(self, topic, payload):
        ok, message = self.publish_mqtt(topic, payload)
        if ok:
            self.indicator_on = payload['state'] == 'ON'
        return ok, message

    def _drive_indicator(self, entity_id, topic, payload, snapshot):
        command = self.indicator_command
        if command is None or (command.entity_id, command.topic, command.payload) != (entity_id, topic, payload):
            command = self.indicator_command = self._new_command(entity_id, topic, payload)
        elif command.observed_at is not None:
            opposite = self._matching_observation(command, {"switch_state": lambda value:
                type(value) is bool and value != (payload['state'] == 'ON')}, after=command.observed_at)
            if opposite is not None:
                command = self.indicator_command = self._new_command(entity_id, topic, payload)
        expected = {"switch_state": lambda value: type(value) is bool and value == (payload['state'] == 'ON')}
        if payload['state'] == 'ON':
            expected['brightness'] = lambda value: value == payload['brightness']
            expected['color'] = lambda value: isinstance(value, dict) and all(
                abs(float(value.get(k, -1))-v) <= .01 for k, v in payload['color'].items())
        if snapshot.get('indicator', {}).get('radio_online') is not False:
            observed = self._matching_observation(command, expected)
            if observed is not None:
                command.observed_at = observed
                self.indicator_on = payload['state'] == 'ON'
        return command.attempt(self._publish_indicator)

    def _indicator(self, snapshot, now):
        with self.command_lock:
            indicator_id = snapshot["bindings"].get("combustion_indicator")
            row = self.fetch_one("select topic_base from hc.entity where id=%s and is_active=true", (indicator_id,)) if indicator_id else None
            if not row or not row.get("topic_base"):
                return
            topic = row["topic_base"] + "/set"
            level = snapshot["level"]
            if level in {"co_warning", "danger", "latched"}:
                self._drive_indicator(indicator_id, topic, {"state": "ON", "brightness": int(snapshot["config"].get("red_brightness", 254)),
                    "color": self._hex_to_xy(snapshot["config"].get("red_color", "#ff0000"))}, snapshot)
                return
            command = self.indicator_command
            pending_off = command and command.payload['state'] == 'OFF' and command.observed_at is None
            pulse_ended = command and command.payload['state'] == 'ON' and self.pulse_off_at and now >= self.pulse_off_at
            if pending_off or pulse_ended or (self.indicator_on and now >= self.pulse_off_at):
                self._drive_indicator(indicator_id, topic, {"state": "OFF"}, snapshot)
                if self.indicator_command.observed_at is None:
                    return
                self.pulse_off_at = 0.0
            if level not in {"green", "secondary", "closed"}:
                return
            intervals = {"green": "green_interval_seconds", "secondary": "secondary_interval_seconds", "closed": "closed_interval_seconds"}
            # An ON retry keeps the same budget and pulse deadline. Do not turn
            # a failure into a newly scheduled successful signal every tick.
            pending_on = self.indicator_command and self.indicator_command.payload['state'] == 'ON'
            if not pending_on and now - self.last_signal_at < float(snapshot["config"][intervals[level]]):
                return
            color_key = "green_color" if level == "green" else "orange_color"
            brightness_key = "green_brightness" if level == "green" else "orange_brightness"
            previous = self.indicator_command
            ok = self._drive_indicator(indicator_id, topic, {"state": "ON",
                "brightness": int(snapshot["config"].get(brightness_key, 50 if level == "green" else 200)),
                "color": self._hex_to_xy(snapshot["config"].get(color_key, "#00ff00" if level == "green" else "#ff8c00"))}, snapshot)
            if previous is not self.indicator_command or not self.pulse_off_at:
                self.pulse_off_at = now + float(snapshot["config"].get("pulse_seconds", 1))
            if ok:
                self.last_signal_at = now

    def _shutdown(self, snapshot):
        with self.command_lock:
            entity_id = snapshot["bindings"].get("combustion_extractor")
            command = self.shutdown_command
            if command and command.entity_id != entity_id:
                self.shutdown_command = command = None
                self.shutdown_sent = False
            row = self.fetch_one("select topic_base from hc.entity where id=%s and is_active=true", (entity_id,)) if entity_id else None
            if not row or not row.get('topic_base'):
                return
            topic = row['topic_base'] + '/set'
            if command and command.topic != topic:
                self.shutdown_command = command = None
                self.shutdown_sent = False
            off_w = float(snapshot['config']['fan_off_w'])
            numeric = lambda value: type(value) in (int, float) and math.isfinite(value)
            if command:
                observed = self._matching_observation(command, {"power": lambda value: numeric(value) and value <= off_w})
                if observed is None:
                    observed = self._matching_observation(command, {"power_w": lambda value: numeric(value) and value <= off_w})
                if observed is not None:
                    command.observed_at = observed
                    return
            if not (snapshot['config'].get('enabled') and snapshot['config'].get('auto_shutdown') and snapshot['danger']):
                return
            if command and command.observed_at is not None:
                # Only a later fresh running measurement can open a new episode.
                on_w = float(snapshot['config']['fan_on_w'])
                running = any(self._matching_observation(command, {key: lambda value: numeric(value) and value >= on_w},
                              after=command.observed_at) is not None for key in ('power', 'power_w'))
                if not running or not snapshot['fan_active']:
                    return
                self.shutdown_command = command = None
                self.shutdown_sent = False
            if not snapshot['fan_active'] and command is None:
                self.shutdown_sent = False
                return
            if command is None:
                command = self.shutdown_command = self._new_command(entity_id, topic, {'state': 'OFF'})
            command.attempt(self.publish_mqtt)
            self.shutdown_sent = command.published

    def _publish_snapshot(self, snapshot, evaluated_at):
        with self._snapshot_lock:
            self._snapshot = deepcopy(snapshot)
            self._evaluated_monotonic = evaluated_at

    def tick(self):
        if not self._tick_lock.acquire(blocking=False):
            return self.state_payload()
        try:
            with self._decision_lock:
                return self._tick()
        finally:
            self._tick_lock.release()

    def _tick(self):
        now = time.time()
        errors = []
        try:
            self._restore_runtime()
        except Exception as exc:
            self.latched = True
            errors.append(str(exc))
        try:
            snapshot = self._evaluate(now)
        except Exception as exc:
            # An unreadable decision cannot publish a healthy/cleared state.
            self.latched = self._pending_latch = True
            snapshot = deepcopy(self._snapshot)
            snapshot.update(ok=False, level='latched', would_level='latched', latched=True,
                            reason='safety evaluation failed', input_health={}, fan_active=None)
            errors.append(str(exc))
        try:
            self._save_runtime()
        except Exception as exc:
            self._runtime_loaded = False
            self.latched = True
            snapshot.update(latched=True, ok=False)
            if snapshot.get('config'):
                self._set_level(snapshot)
            errors.append(str(exc))
        snapshot['persistence'] = {'restored': self._runtime_loaded, 'revision': self._runtime_revision,
                                   'error': '; '.join(errors) or None}
        snapshot['evaluation_error'] = '; '.join(errors) or None
        snapshot['evaluated_at_epoch'] = now
        evaluated_at = time.monotonic()
        # Publish the complete decision before potentially slow actuation/log I/O.
        self._publish_snapshot(snapshot, evaluated_at)
        if snapshot.get('bindings') and snapshot.get('config'):
            for name, action in (("shutdown", lambda: self._shutdown(snapshot)), ("indicator", lambda: self._indicator(snapshot, now))):
                try:
                    action()
                except Exception as exc:
                    print(f"[COMBUSTION] {name} error: {exc}", flush=True)
            snapshot['actuation'] = self._actuation_payload()
            snapshot.setdefault('signal', {}).update(indicator_on=self.indicator_on, last_signal_at_epoch=self.last_signal_at,
                                                       pulse_off_at_epoch=self.pulse_off_at)
        try:
            if snapshot['level'] != self.last_level:
                self.execute_one(
                    "insert into hc.combustion_safety_event(level,event_type,reason,payload) values(%s,'state_change',%s,%s::jsonb) returning id",
                    (snapshot['level'], snapshot['reason'], __import__('json').dumps({k: snapshot.get(k) for k in
                        ('fan_active','power_w','primary_open','secondary_open','co','indicator','smoke','latched')}, default=str)))
                self.last_level = snapshot['level']
            snapshot['events'] = self.fetch_all("select id,ts,level,event_type,reason,payload from hc.combustion_safety_event order by ts desc limit 50")
        except Exception as exc:
            snapshot['event_error'] = str(exc)
            snapshot.setdefault('events', [])
        self._publish_snapshot(snapshot, evaluated_at)
        return self.state_payload()

    def state_payload(self):
        # No DB, publish, evaluation, debounce, latch or history writes on GET.
        with self._snapshot_lock:
            snapshot = deepcopy(self._snapshot)
            evaluated_at = self._evaluated_monotonic
        age = None if evaluated_at is None else max(0, time.monotonic()-evaluated_at)
        stale = age is None or age > self.snapshot_max_age_seconds
        snapshot.update(evaluation_age_seconds=age, stale=stale)
        if stale:
            snapshot.update(ok=False, fan_active=None, reason='safety evaluation missing or stale')
            snapshot['level'] = 'latched' if snapshot.get('latched') else 'unknown'
        elif not snapshot.get('input_health', {}).get('fan'):
            # Unknown power must not grant a climate-window extractor exemption.
            snapshot['fan_active'] = None
        return snapshot

    def update_config(self, data, updated_by="api"):
        allowed = {"enabled", "fan_on_w", "fan_off_w", "fan_on_seconds", "fan_off_seconds", "co_warning_ppm", "co_shutdown_ppm", "co_rise_ppm", "auto_shutdown", "green_interval_seconds", "secondary_interval_seconds", "closed_interval_seconds", "pulse_seconds", "green_brightness", "orange_brightness", "red_brightness", "green_color", "orange_color", "red_color"}
        current = self.config()
        values = {key: data.get(key, current.get(key)) for key in allowed}
        if float(values["fan_off_w"]) >= float(values["fan_on_w"]): raise ValueError("fan_off_w must be below fan_on_w")
        if float(values["co_warning_ppm"]) > float(values["co_shutdown_ppm"]): raise ValueError("co_warning_ppm must not exceed co_shutdown_ppm")
        for key in ("green_brightness", "orange_brightness", "red_brightness"):
            if not 1 <= int(values[key]) <= 254: raise ValueError(f"{key} must be between 1 and 254")
        for key in ("green_color", "orange_color", "red_color"):
            self._hex_to_xy(values[key])
        return self.execute_one("""
          update hc.combustion_safety_config set enabled=%s,fan_on_w=%s,fan_off_w=%s,fan_on_seconds=%s,fan_off_seconds=%s,
          co_warning_ppm=%s,co_shutdown_ppm=%s,co_rise_ppm=%s,auto_shutdown=%s,green_interval_seconds=%s,
          secondary_interval_seconds=%s,closed_interval_seconds=%s,pulse_seconds=%s,green_brightness=%s,orange_brightness=%s,
          red_brightness=%s,green_color=%s,orange_color=%s,red_color=%s,updated_at=now(),updated_by=%s where singleton=true returning *
        """, (bool(values["enabled"]),float(values["fan_on_w"]),float(values["fan_off_w"]),int(values["fan_on_seconds"]),int(values["fan_off_seconds"]),float(values["co_warning_ppm"]),float(values["co_shutdown_ppm"]),float(values["co_rise_ppm"]),bool(values["auto_shutdown"]),int(values["green_interval_seconds"]),int(values["secondary_interval_seconds"]),int(values["closed_interval_seconds"]),float(values["pulse_seconds"]),int(values["green_brightness"]),int(values["orange_brightness"]),int(values["red_brightness"]),str(values["green_color"]).lower(),str(values["orange_color"]).lower(),str(values["red_color"]).lower(),updated_by))

    def acknowledge(self):
        # Explicit manual clear is serialized with the sole decision owner.
        # It never calls evaluate or advances debounce/CO history.
        with self._decision_lock:
            snapshot = self.state_payload()
            if snapshot['stale'] or not self._runtime_loaded or snapshot.get('evaluation_error'):
                raise ValueError('fresh restored worker state is required before acknowledgement')
            if snapshot.get('danger'):
                raise ValueError('active CO/smoke danger cannot be acknowledged')
            ids = {key: self.binding_entity_id(key) for key in snapshot['bindings']}
            if ids != snapshot['bindings']:
                raise ValueError('bindings changed; wait for the next worker evaluation')
            config = self.config()
            co = self._state(ids['combustion_co_sensor'], ('carbon_monoxide', 'carbon_monoxide_value', 'co', 'co_ppm', 'fault'))
            smoke = self._state(ids['combustion_smoke_sensor'], ('smoke', 'smoke_alarm', 'fire', 'alarm'))
            row = self.fetch_one("select d.ext_id from hc.entity e join hc.device d on d.id=e.device_id where e.id=%s", (ids['combustion_co_sensor'],)) if ids['combustion_co_sensor'] else None
            radio = self.zigbee_radio_status(row['ext_id']) if row else {}
            health = self._clear_inputs(ids, co, smoke, radio, time.time(), self._radio_for(ids['combustion_smoke_sensor']))
            if not health['co'] or not health['smoke']:
                raise ValueError('known CO/smoke states without faults and confirmed radio presence are required')
            danger = self._truthy((co.get('carbon_monoxide') or {}).get('value')) or any(self._truthy(v['value']) for v in smoke.values())
            danger = danger or any(float(v['value']) >= float(config.get('co_shutdown_ppm', 20)) for k, v in co.items()
                                   if k in ('carbon_monoxide_value', 'co', 'co_ppm'))
            if danger or self.state_payload()['stale']:
                raise ValueError('danger or stale worker state cannot be acknowledged')
            old_latch = self.latched
            self.latched = False
            try:
                self._save_runtime(acknowledge=True)
            except Exception as exc:
                self.latched = old_latch
                self._runtime_loaded = False
                self._pending_latch = old_latch
                snapshot.update(ok=False, latched=old_latch,
                                evaluation_error='acknowledgement persistence uncertain',
                                persistence={'restored': False, 'revision': self._runtime_revision, 'error': str(exc)})
                self._set_level(snapshot)
                self._publish_snapshot(snapshot, self._evaluated_monotonic)
                raise
            snapshot.update(latched=False)
            snapshot['persistence'] = {'restored': True, 'revision': self._runtime_revision, 'error': None}
            self._set_level(snapshot)
            # Keep the worker evaluation timestamp/age: an ACK is not a new sample.
            self._publish_snapshot(snapshot, self._evaluated_monotonic)
            return self.state_payload()

    def preview_indicator(self, pattern: str):
        allowed = {"green", "secondary", "closed", "red", "off"}
        if pattern not in allowed:
            raise ValueError("pattern must be green, secondary, closed, red or off")
        indicator_id = self.binding_entity_id("combustion_indicator")
        row = self.fetch_one("select topic_base from hc.entity where id=%s and is_active=true", (indicator_id,)) if indicator_id else None
        if not row or not row.get("topic_base"):
            raise ValueError("combustion indicator is not configured")
        config = self.config()
        if pattern != "off" and config.get("enabled"):
            raise ValueError("disable the guard before running a light preview")
        topic = row["topic_base"] + "/set"
        with self.preview_lock:
            self.preview_generation += 1
            generation = self.preview_generation
        if pattern == "off":
            with self.command_lock:
                self.indicator_command = None
            ok, message = self._publish_indicator(topic, {"state": "OFF"})
            return {"ok": bool(ok), "pattern": pattern, "message": message, "cancelled_preview": True}

        def active():
            with self.preview_lock:
                return generation == self.preview_generation

        def run():
            if pattern == "red":
                self._publish_indicator(topic, {"state": "ON", "brightness": int(config.get("red_brightness", 254)), "color": self._hex_to_xy(config.get("red_color", "#ff0000"))})
                self.pulse_off_at = time.time() + 5
                time.sleep(5)
                if active():
                    self._publish_indicator(topic, {"state": "OFF"})
                return
            color = self._hex_to_xy(config.get("green_color", "#00ff00") if pattern == "green" else config.get("orange_color", "#ff8c00"))
            brightness = int(config.get("green_brightness" if pattern == "green" else "orange_brightness", 50 if pattern == "green" else 200))
            interval = 5 if pattern == "green" else int(config.get("secondary_interval_seconds" if pattern == "secondary" else "closed_interval_seconds", 20 if pattern == "secondary" else 4))
            pulse = float(config.get("pulse_seconds", 1))
            for cycle in range(3):
                if not active(): return
                self._publish_indicator(topic, {"state": "ON", "brightness": brightness, "color": color})
                self.pulse_off_at = time.time() + pulse
                time.sleep(pulse)
                if not active(): return
                self._publish_indicator(topic, {"state": "OFF"})
                if cycle < 2:
                    time.sleep(max(0, interval - pulse))

        thread = threading.Thread(target=run, name=f"combustion-light-preview-{pattern}", daemon=True)
        thread.start()
        return {"ok": True, "pattern": pattern, "cycles": 1 if pattern == "red" else 3,
                "interval_seconds": 5 if pattern == "green" else (5 if pattern == "red" else int(config.get("secondary_interval_seconds" if pattern == "secondary" else "closed_interval_seconds"))),
                "green_interval_accelerated": pattern == "green"}
