import json
import unittest
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from irrigation_service import IrrigationService


def noop(*args, **kwargs):
    return None


class IrrigationServiceTest(unittest.TestCase):
    def service(self, **overrides):
        published = []
        invalidated = []
        defaults = {
            "fetch_all": lambda *args, **kwargs: [],
            "fetch_one": lambda *args, **kwargs: None,
            "execute_one": lambda *args, **kwargs: None,
            "execute_sql": noop,
            "publish_mqtt": lambda topic, payload: published.append((topic, payload)) or (True, "published"),
            "normalize_text": lambda value, default="": str(value or "").strip() or default,
            "command_topics": lambda: {
                "valve": "cmd/valve",
                "system": "cmd/system",
                "mode": "cmd/mode",
                "pump": "cmd/pump",
                "config": "cmd/config",
            },
            "invalidate_snapshot": lambda: invalidated.append("irrigation"),
            "invalidate_pilot": lambda: invalidated.append("irrigation_pilot"),
            "invalidate_weather_summary": lambda: invalidated.append("weather_summary"),
            "invalidate_context": lambda *sections, **kwargs: invalidated.extend(sections),
            "context_meta": lambda *sections: {
                "invalidated": list(sections),
                "read_after": [f"/api/context/{section}" for section in sections],
            },
            "ensure_pilot_schema": noop,
            "to_float": lambda value, default=None: float(value if value is not None else default),
            "to_int": lambda value, default=0: int(value if value is not None else default),
            "manual_max_minutes": 180,
            "api_cache_get": lambda key: None,
            "api_cache_set": lambda key, data, ttl: data,
            "api_cache_delete_prefix": noop,
            "mqtt_snapshot": lambda: {"mqtt_connected": True, "connection_generation": 1, "topics": {}},
            "scheduler_config": lambda: {},
            "v2_execution_engine_state": lambda config: {"publish_domains": []},
            "json_time": lambda value: value.isoformat() if hasattr(value, "isoformat") else value,
            "stop_confirm_attempts": 1,
            "stop_reaction_delay_seconds": 0,
            "stop_closed_delay_seconds": 0,
            "open_confirm_attempts": 1,
            "open_reaction_delay_seconds": 0,
            "open_ready_delay_seconds": 0,
            "openweather_api_key": "",
            "openweather_lat": "",
            "openweather_lon": "",
            "openweather_units": "metric",
            "openweather_lang": "hu",
            "weather_poll_seconds": 3600,
            "absolute_humidity_g_m3": lambda temperature, humidity: None,
            "pilot_cache_ttl": 300,
            "weather_summary_cache_ttl": 300,
            "daily_summary_days": 35,
            "daily_summary_refresh_sec": 300,
            "snapshot_ttl": 10,
        }
        defaults.update(overrides)
        service = IrrigationService(**defaults)
        if "reserve_session" not in overrides:
            # Service tests fake admission; PostgreSQL tests exercise the real
            # transactional implementation, not this SQL-shaped fixture.
            def reserve(**values):
                row = service.execute_one(
                    "insert into hc.irrigation_manual_session /* fixture admission */ returning *",
                    (values['minutes'], values['safety_minutes'], values['started_by'],
                     json.dumps(values['start_payload'])),
                )
                return {"session": row, "blocked_by": None}
            service.reserve_session = reserve
        # General domain tests start after a successful, empty recovery scan.
        service.session_recovery.initialized = True
        service.published = published
        service.invalidated = invalidated
        return service

    def test_unknown_command_returns_400_without_publish(self):
        service = self.service()

        payload, status = service.command({"name": "does_not_exist"})

        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(service.published, [])

    def test_ping_command_publishes_and_invalidates_irrigation(self):
        service = self.service()

        payload, status = service.command({"name": "ping"})

        self.assertEqual(status, 200)
        self.assertEqual(service.published, [("cmd/system", {"cmd": "ping"})])
        self.assertEqual(service.invalidated, ["irrigation"])
        self.assertEqual(payload["context"]["read_after"], ["/api/context/irrigation"])

    def test_winter_profile_blocks_manual_start_without_database_or_publish(self):
        service = self.service(control_allowed=lambda: False)

        payload, status = service.start_manual({"duration_minutes": 20})

        self.assertEqual(status, 423)
        self.assertEqual(payload["blocked_by"], "season_profile")
        self.assertEqual(service.published, [])

    def test_winter_profile_keeps_safe_close_and_status_commands_available(self):
        service = self.service(control_allowed=lambda: False)
        service.publish_stop_with_confirmation = lambda source: (True, "closed", {})

        close_payload, close_status = service.command({"name": "valve_close"})
        status_payload, status_status = service.command({"name": "valve_status"})

        self.assertEqual(close_status, 200)
        self.assertTrue(close_payload["ok"])
        self.assertEqual(status_status, 200)
        self.assertTrue(status_payload["ok"])
        self.assertEqual(service.published, [("cmd/valve", {"cmd": "status"})])

    def test_filter_isolated_tank_level_spike(self):
        base = datetime(2026, 8, 30, 12, 0)
        rows = [
            {"ts": base, "level_percent": 60},
            {"ts": base + timedelta(minutes=5), "level_percent": 100},
            {"ts": base + timedelta(minutes=10), "level_percent": 61},
        ]

        cleaned, filtered = IrrigationService.filter_isolated_tank_level_spikes(rows)

        self.assertEqual(filtered, 1)
        self.assertIsNone(cleaned[1]["level_percent"])
        self.assertEqual(cleaned[1]["level_percent_raw"], 100)
        self.assertEqual(rows[1]["level_percent"], 100)

    def test_filter_keeps_real_tank_fill(self):
        base = datetime(2026, 8, 30, 12, 0)
        rows = [
            {"ts": base, "level_percent": 60},
            {"ts": base + timedelta(minutes=5), "level_percent": 100},
            {"ts": base + timedelta(minutes=10), "level_percent": 100},
        ]

        cleaned, filtered = IrrigationService.filter_isolated_tank_level_spikes(rows)

        self.assertEqual(filtered, 0)
        self.assertEqual([row["level_percent"] for row in cleaned], [60, 100, 100])

    def test_pump_current_live_snapshot_maps_mqtt_payload(self):
        service = self.service(
            mqtt_snapshot=lambda: {
                "topics": {
                    "pump_metrics": {
                        "age_sec": 1,
                        "topic": "homecontrol/tele/irrigation/esp-irrigation-1/pump_metrics",
                        "json": {
                            "current_a": "1.23",
                            "pump": "1",
                            "voltage_12v": "13.4",
                            "temp_c": "29.8",
                            "valve": "OPEN",
                            "manual_valve": "CLOSED",
                        },
                    }
                }
            }
        )

        payload = service.pump_current_live_snapshot()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["type"], "irrigation_pump_current")
        self.assertEqual(payload["pump_current_a"], 1.23)
        self.assertEqual(payload["max_pump_current_a"], 1.23)
        self.assertEqual(payload["pump"], 1)
        self.assertEqual(payload["age_sec"], 1.0)

    def test_nano_config_requires_key(self):
        service = self.service()

        payload, status = service.nano_config({"value": "1"})

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "missing key")
        self.assertEqual(service.published, [])

    def test_stop_manual_without_running_session_returns_404(self):
        service = self.service(fetch_one=lambda *args, **kwargs: None)

        payload, status = service.stop_manual({})

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "no running session")

    def test_update_schedule_rejects_inverted_window(self):
        service = self.service()

        payload, status = service.update_schedule(1, {"start_time": "18:00", "stop_time": "06:00"})

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "start_time must be before stop_time")

    def test_live_valve_state_reads_mqtt_monitor_payloads(self):
        received = time.monotonic()
        metadata = {"retain": False, "timestamp": time.time(), "received_monotonic": received, "connection_generation": 1}
        service = self.service(
            mqtt_snapshot=lambda: {
                "mqtt_connected": True,
                "connection_generation": 1,
                "topics": {
                    "pump_metrics": {**metadata, "json": {"valve": "open", "manual_valve": "closed", "valve_current": "0.12", "last_tele_sec_ago": 0}},
                    "esp_nano_status": {**metadata, "json": {"online": True, "last_status_sec_ago": 0}},
                }
            }
        )

        state = service.live_valve_state()

        self.assertEqual(state["valve"], "OPEN")
        self.assertTrue(state["motor_fully_open"])
        self.assertTrue(state["manual_closed"])
        self.assertEqual(state["valve_current_a"], 0.12)

    def test_scheduler_tick_skips_without_irrigation_publish_domain(self):
        calls = []
        service = self.service()
        service.run_due_schedules = lambda: calls.append("run_legacy")
        service.stop_due_schedules = lambda: calls.append("stop_legacy")
        service.run_v2_due_schedules = lambda: calls.append("run_v2")
        service.stop_v2_due_schedules = lambda: calls.append("stop_v2")

        service.scheduler_tick()

        self.assertEqual(calls, [])

    def test_scheduler_tick_uses_v2_branch_for_irrigation_publish_domain(self):
        calls = []
        service = self.service(
            v2_execution_engine_state=lambda config: {"publish_domains": ["irrigation"]},
        )
        service.run_due_schedules = lambda: calls.append("run_legacy")
        service.stop_due_schedules = lambda: calls.append("stop_legacy")
        service.run_v2_due_schedules = lambda: calls.append("run_v2")
        service.stop_v2_due_schedules = lambda: calls.append("stop_v2")
        service.solar_pump_scheduler_tick = lambda: calls.append("pump")

        service.scheduler_tick()

        self.assertEqual(calls, ["run_v2", "pump"])

    def test_scheduler_stop_tick_uses_v2_stop_without_starting(self):
        calls = []
        service = self.service(v2_execution_engine_state=lambda config: {"publish_domains": ["irrigation"]})
        service.stop_v2_due_schedules = lambda: calls.append("stop_v2")
        service.run_v2_due_schedules = lambda: self.fail("stop tick started watering")
        service.scheduler_stop_tick()
        self.assertEqual(calls, ["stop_v2"])

    def test_scheduler_stop_tick_respects_domain_enablement(self):
        service = self.service()
        service.stop_v2_due_schedules = lambda: self.fail("disabled V2 stop ran")
        service.scheduler_stop_tick()

    def pilot_config(self, **overrides):
        config = {
            "mode": "navigator",
            "base_duration_minutes": 60,
            "rain_24h_threshold_mm": 5,
            "forecast_rain_threshold_mm": 5,
            "pop_threshold_percent": 70,
            "heat_threshold_c": 32,
            "heat_correction_percent": 20,
            "heat_step_c": 5,
            "heat_multiplier_step": 0.1,
            "cold_threshold_c": 22,
            "cold_correction_percent": -20,
            "cold_step_c": 5,
            "cold_multiplier_step": -0.1,
            "soil_moisture_enabled": True,
            "soil_sensor_topic_base": "zigbee/0xa4c13844a0908898",
            "soil_wet_skip_threshold_percent": 85,
            "soil_wet_adjust_threshold_percent": 65,
            "soil_wet_multiplier_delta": -0.5,
            "soil_dry_threshold_percent": 45,
            "soil_dry_correction_percent": 15,
            "soil_dry_multiplier_delta": 0.15,
            "soil_sample_max_age_hours": 12,
            "min_duration_multiplier": 0.2,
            "max_duration_multiplier": 1.5,
        }
        config.update(overrides)
        return config

    def pilot_snapshot(self, soil_moisture=59, soil_age_hours=1, temperature=25):
        return {
            "rain_24h_mm": 0,
            "forecast_rain_24h_mm": 0,
            "pop_percent": 0,
            "temperature_c": temperature,
            "humidity_percent": None,
            "wind_speed_mps": None,
            "uv_index": None,
            "cloudiness_percent": None,
            "pressure_hpa": None,
            "sunrise": None,
            "sunset": None,
            "weather_ts": None,
            "local_sensor": {"temperature_c": None, "humidity_percent": None, "absolute_humidity_g_m3": None},
            "rain_sensor": {"is_wet": False, "last_wet_ts": None, "battery_percent": None, "linkquality": None},
            "soil_moisture_sensor": {
                "name": "Moisture_02",
                "topic_base": "zigbee/0xa4c13844a0908898",
                "soil_moisture_percent": soil_moisture,
                "ts": "now",
                "age_hours": soil_age_hours,
                "sample_count_24h": 12,
                "avg_24h_percent": soil_moisture,
                "min_24h_percent": soil_moisture,
                "max_24h_percent": soil_moisture,
            },
        }

    def test_pilot_skips_when_garden_soil_is_wet(self):
        service = self.service()
        service.fetch_pilot_config = lambda: self.pilot_config()
        service.fetch_pilot_base_schedule = lambda: None
        service.build_weather_snapshot = lambda topic: self.pilot_snapshot(soil_moisture=90)

        decision = service.evaluate_pilot(base_duration=60)

        self.assertEqual(decision["final_duration"], 0)
        self.assertEqual(decision["triggered_rules"], ["soil_wet_skip"])
        self.assertTrue(decision["details"]["rules"]["soil_wet_skip"])

    def test_pilot_increases_when_garden_soil_is_dry(self):
        service = self.service()
        service.fetch_pilot_config = lambda: self.pilot_config()
        service.fetch_pilot_base_schedule = lambda: None
        service.build_weather_snapshot = lambda topic: self.pilot_snapshot(soil_moisture=40)

        decision = service.evaluate_pilot(base_duration=60)

        self.assertEqual(decision["final_duration"], 69)
        self.assertEqual(decision["triggered_rules"], ["soil_dry_increase"])
        self.assertEqual(decision["details"]["result"]["corrections"][0]["minutes"], 9)

    def test_pilot_combines_heat_and_wet_soil_multiplier(self):
        service = self.service()
        service.fetch_pilot_config = lambda: self.pilot_config()
        service.fetch_pilot_base_schedule = lambda: None
        service.build_weather_snapshot = lambda topic: self.pilot_snapshot(soil_moisture=65, temperature=42)

        decision = service.evaluate_pilot(base_duration=90)

        self.assertEqual(decision["final_duration"], 72)
        self.assertEqual(decision["triggered_rules"], ["heat_increase", "soil_wet_reduce"])
        self.assertEqual(decision["details"]["result"]["raw_multiplier"], 0.8)
        self.assertEqual(decision["details"]["result"]["applied_multiplier"], 0.8)

    def test_pilot_ignores_stale_garden_soil_sample(self):
        service = self.service()
        service.fetch_pilot_config = lambda: self.pilot_config()
        service.fetch_pilot_base_schedule = lambda: None
        service.build_weather_snapshot = lambda topic: self.pilot_snapshot(soil_moisture=90, soil_age_hours=13)

        decision = service.evaluate_pilot(base_duration=60)

        self.assertEqual(decision["final_duration"], 60)
        self.assertEqual(decision["triggered_rules"], [])
        self.assertFalse(decision["details"]["inputs"]["SoilMoistureUsable"])


class IrrigationConfirmationTest(unittest.TestCase):
    def setUp(self):
        self.clock = 1000.0
        self.wall = 1800000000.0
        self.on_publish = lambda: None
        self.on_sleep = lambda: None
        self.published = []
        self.live = {"mqtt_connected": True, "connection_generation": 1, "topics": {}}
        self.addCleanup(patch.stopall)
        patch("time.monotonic", side_effect=lambda: self.clock).start()
        patch("time.time", side_effect=lambda: self.wall + self.clock - 1000).start()
        patch("time.sleep", side_effect=self.sleep).start()
        self.service = IrrigationServiceTest().service(
            mqtt_snapshot=lambda: self.live, publish_mqtt=self.publish,
        )
        self.live["topics"]["esp_nano_status"] = self.sample(online=True)

    def sleep(self, seconds):
        self.clock += seconds
        self.on_sleep()

    def publish(self, topic, payload):
        self.published.append((topic, payload))
        self.on_publish()
        return True, "published"

    def sample(self, value=None, age=0, received_ago=0, **payload):
        return {
            "topic": "audit/irrigation/telemetry",
            "retain": False,
            "timestamp": time.time() - received_ago,
            "received_monotonic": self.clock - received_ago,
            "connection_generation": self.live["connection_generation"],
            "json": {"valve": value, "manual_valve": "CLOSED", "valve_current": 0,
                     "last_tele_sec_ago": age, "last_status_sec_ago": age, **payload},
        }

    def respond(self, value, source="pump_metrics", age=0, **payload):
        # >1 second distinguishes a new sample even with integer age counters.
        self.clock += 2
        self.live["topics"][source] = self.sample(value, age=age, **payload)

    def confirm(self, value):
        if value == "OPEN":
            return self.service.publish_open_with_confirmation({"value": "open", "source": "manual"})
        return self.service.publish_stop_with_confirmation("audit-test")

    def test_cached_retained_closed_is_not_confirmation(self):
        self.live["topics"]["pump_metrics"] = {**self.sample("CLOSED", received_ago=86400), "retain": True}
        ok, _, details = self.confirm("CLOSED")
        self.assertFalse(ok)
        self.assertEqual(len(self.published), 1)
        self.assertFalse(details["attempts"][0]["reaction_seen"])

    def test_cached_nonretained_state_does_not_confirm_a_new_command(self):
        for value in ("OPEN", "CLOSED"):
            with self.subTest(value=value):
                self.live["topics"]["pump_metrics"] = self.sample(value)
                self.assertFalse(self.confirm(value)[0])

    def test_fresh_postcommand_open_and_closed_confirm(self):
        for value in ("OPEN", "CLOSED"):
            with self.subTest(value=value):
                self.on_publish = lambda: self.respond(value)
                ok, _, details = self.confirm(value)
                self.assertTrue(ok)
                state = details["attempts"][0]["reaction_state"]
                self.assertEqual(state["observations"]["valve"]["source"], "pump_metrics")
                self.assertTrue(state["nano_online"])

    def test_new_mqtt_republication_of_precommand_nano_sample_does_not_confirm(self):
        for value in ("OPEN", "CLOSED"):
            with self.subTest(value=value):
                self.on_publish = lambda: self.respond(value, age=3)
                ok, _, details = self.confirm(value)
                self.assertFalse(ok)
                evidence = details["attempts"][0]["reaction_state"]["sources"]["pump_metrics"]
                self.assertEqual(evidence["rejected_reason"], "sample_not_proven_after_command")

    def test_subsecond_age_zero_is_not_proof_of_postcommand_sampling(self):
        def immediate_republication():
            self.clock += .25
            self.live["topics"]["pump_metrics"] = self.sample("CLOSED")
        self.on_publish = immediate_republication
        self.assertFalse(self.confirm("CLOSED")[0])

    def test_postcommand_retained_message_does_not_confirm(self):
        def reply():
            self.respond("CLOSED")
            self.live["topics"]["pump_metrics"]["retain"] = True
        self.on_publish = reply
        self.assertFalse(self.confirm("CLOSED")[0])

    def test_disconnected_monitor_does_not_confirm_but_still_sends_close(self):
        self.live["mqtt_connected"] = False
        self.on_publish = lambda: self.respond("CLOSED")
        self.assertFalse(self.confirm("CLOSED")[0])
        self.assertEqual(len(self.published), 1)
        self.assertEqual(self.published[0][1]["value"], "close")

    def test_reconnect_does_not_revalidate_previous_connection_samples(self):
        self.live["topics"]["pump_metrics"] = self.sample("CLOSED")
        self.live["connection_generation"] += 1
        state = self.service.live_valve_state()
        self.assertFalse(state["motor_closed"])
        self.assertIsNone(state["nano_online"])
        self.assertEqual(state["sources"]["pump_metrics"]["rejected_reason"], "previous_or_unknown_connection")

    def test_fresh_status_can_confirm_without_periodic_tele(self):
        self.on_publish = lambda: self.respond("CLOSED", source="esp_nano_status", online=True)
        ok, _, details = self.confirm("CLOSED")
        self.assertTrue(ok)
        state = details["attempts"][0]["reaction_state"]
        self.assertIsNone(state["tele_fresh"])
        self.assertTrue(state["status_fresh"])
        self.assertEqual(state["observations"]["valve"]["source"], "esp_nano_status")

    def test_fresh_status_wins_over_stale_primary_topic(self):
        self.live["topics"]["pump_metrics"] = self.sample("OPEN", age=26)
        self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", age=1, online=True)
        state = self.service.live_valve_state()
        self.assertTrue(state["motor_closed"])
        self.assertFalse(state["tele_fresh"])
        self.assertTrue(state["status_fresh"])

    def test_freshest_nano_sample_wins_over_freshest_mqtt_receipt(self):
        self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", received_ago=2, online=True)
        self.live["topics"]["pump_metrics"] = self.sample("OPEN", age=10)
        state = self.service.live_valve_state()
        self.assertTrue(state["motor_closed"])
        self.assertEqual(state["observations"]["valve"]["source"], "esp_nano_status")

    def test_source_age_increases_with_elapsed_receipt_time(self):
        self.live["topics"]["pump_metrics"] = self.sample("OPEN", age=24)
        self.assertTrue(self.service.live_valve_state()["tele_fresh"])
        self.clock += 2
        state = self.service.live_valve_state()
        self.assertFalse(state["tele_fresh"])
        self.assertEqual(state["sources"]["pump_metrics"]["age_sec"], 26)

    def test_status_and_tele_have_independent_configurable_age_limits(self):
        self.live["topics"]["pump_metrics"] = self.sample("OPEN", age=26)
        self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", age=69, online=True)
        state = self.service.live_valve_state()
        self.assertFalse(state["tele_fresh"])
        self.assertTrue(state["status_fresh"])
        self.assertTrue(state["nano_online"])
        self.service.valve_tele_max_age_seconds = 27
        self.service.valve_status_max_age_seconds = 68
        state = self.service.live_valve_state()
        self.assertTrue(state["tele_fresh"])
        self.assertFalse(state["status_fresh"])
        self.assertTrue(state["nano_online"])

    def test_online_true_expires_independently_of_status_sample(self):
        self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", received_ago=41, online=True)
        self.live["topics"]["pump_metrics"] = self.sample("OPEN")
        state = self.service.live_valve_state()
        self.assertTrue(state["status_fresh"])
        self.assertTrue(state["tele_fresh"])
        self.assertIsNone(state["nano_online"])
        self.assertFalse(state["motor_fully_open"])
        self.service.nano_online_max_age_seconds = 42
        self.assertTrue(self.service.live_valve_state()["nano_online"])

    def test_pump_and_diag_online_flags_cannot_override_status_offline_or_unknown(self):
        for online in (False, None):
            with self.subTest(online=online):
                self.live["topics"]["esp_nano_status"] = self.sample(online=online)
                self.live["topics"]["pump_metrics"] = self.sample("OPEN", online=True, nano_online=True)
                self.live["topics"]["diag"] = self.sample(nano_online=True)
                state = self.service.live_valve_state()
                self.assertIs(state["nano_online"], online)
                self.assertFalse(state["motor_fully_open"])

    def test_missing_invalid_and_future_sample_metadata_cannot_confirm(self):
        for age in (None, -1, "bad", float("nan"), float("inf"), True):
            with self.subTest(age=age):
                self.on_publish = lambda: self.respond("CLOSED", age=age)
                self.assertFalse(self.confirm("CLOSED")[0])
        for key, value in (("received_monotonic", None), ("received_monotonic", self.clock + 100),
                           ("timestamp", None), ("connection_generation", None), ("retain", None)):
            with self.subTest(key=key, value=value):
                def reply():
                    self.respond("CLOSED")
                    self.live["topics"]["pump_metrics"][key] = value
                self.on_publish = reply
                self.assertFalse(self.confirm("CLOSED")[0])

    def test_invalid_payload_position_or_current_cannot_fake_confirmation(self):
        for payload in ("malformed", {"valve": "NOT_CLOSED", "last_tele_sec_ago": 0},
                        {"valve_current": "bad", "last_tele_sec_ago": 0}):
            with self.subTest(payload=payload):
                def reply():
                    self.respond("CLOSED")
                    self.live["topics"]["pump_metrics"]["json"] = payload
                self.on_publish = reply
                self.assertFalse(self.confirm("CLOSED")[0])

    def test_late_fresh_feedback_is_accepted_with_existing_waits(self):
        self.service.stop_reaction_delay_seconds = 5
        self.service.stop_closed_delay_seconds = 30
        def delayed_reply():
            if self.clock >= 1030:
                self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", online=True)
        self.on_sleep = delayed_reply
        ok, _, details = self.confirm("CLOSED")
        self.assertTrue(ok)
        self.assertFalse(details["attempts"][0]["reaction_state"]["motor_closed"])
        self.assertTrue(details["attempts"][0]["closed_state"]["motor_closed"])
        self.assertEqual(self.clock, 1030)

    def test_feedback_arriving_after_final_check_does_not_retroactively_confirm(self):
        self.service.stop_closed_delay_seconds = 30
        self.assertFalse(self.confirm("CLOSED")[0])
        self.respond("CLOSED", source="esp_nano_status", online=True)
        # A new command needs its own subsequent sample.
        self.assertFalse(self.confirm("CLOSED")[0])

    def test_retry_needs_a_sample_after_that_attempt(self):
        self.service.stop_confirm_attempts = 2
        def reply():
            self.clock += 2
            self.live["topics"]["esp_nano_status"] = self.sample(online=True)
            self.live["topics"]["pump_metrics"] = self.sample("CLOSED", age=3 if len(self.published) == 1 else 2)
        self.on_publish = reply
        ok, _, details = self.confirm("CLOSED")
        self.assertFalse(ok)
        self.assertEqual(len(details["attempts"]), 2)

    def test_wall_clock_change_does_not_refresh_an_old_sample(self):
        self.live["topics"]["pump_metrics"] = self.sample("CLOSED")
        self.clock += 26
        self.wall -= 3600
        self.assertFalse(self.service.live_valve_state()["tele_fresh"])

    def test_no_watering_check_ignores_stale_samples_and_samples_before_session(self):
        updates = []
        self.service.execute_one = lambda *args: updates.append(args)
        self.service.fetch_all = lambda *args: [{"id": 1, "started_at": datetime.fromtimestamp(time.time() - 120, timezone.utc)}]
        self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", age=71, online=True)
        self.service.fail_sessions_without_physical_watering()
        self.assertEqual(updates, [])
        self.service.valve_status_max_age_seconds = 200
        self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", age=130, online=True)
        self.service.fail_sessions_without_physical_watering()
        self.assertEqual(updates, [])
        self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", online=True)
        self.service.fail_sessions_without_physical_watering()
        self.assertEqual(len(updates), 1)
        self.assertIn("failed_no_watering", updates[0][0])

    def test_failed_confirmation_is_stored_as_stop_failed(self):
        updates = []
        self.live["topics"]["pump_metrics"] = self.sample("CLOSED")
        self.service.execute_one = lambda *args: updates.append(args) or {"id": 1}
        ok, _, _ = self.service.stop_manual_session(1, "manual_stop")
        self.assertFalse(ok)
        self.assertEqual(updates[0][1][0], "stop_failed")

    def test_stale_open_feedback_cannot_promote_a_session_to_running(self):
        updates = []
        self.live["topics"]["pump_metrics"] = self.sample("OPEN")
        self.service.execute_one = lambda *args: updates.append(args) or {"id": 1}
        payload, status = self.service.start_manual({"duration_minutes": 10})
        self.assertEqual(status, 502)
        self.assertFalse(payload["ok"])
        self.assertIn("stop_failed", updates[-1][0])
        self.assertFalse(any("set status = 'running'" in sql for sql, *_ in updates))

    def test_invalid_online_values_do_not_establish_liveness(self):
        for value in ("true", 1, None):
            with self.subTest(value=value):
                self.live["topics"]["esp_nano_status"] = self.sample("CLOSED", online=value)
                state = self.service.live_valve_state()
                self.assertIsNone(state["nano_online"])
                self.assertFalse(state["motor_closed"])

    def test_invalid_freshness_configuration_is_rejected(self):
        for key in ("valve_tele_max_age_seconds", "valve_status_max_age_seconds", "nano_online_max_age_seconds"):
            for value in (0, -1, float("nan"), float("inf")):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    IrrigationServiceTest().service(**{key: value})


if __name__ == "__main__":
    unittest.main()
