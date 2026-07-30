import unittest
import sys
from pathlib import Path

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
            "mqtt_snapshot": lambda: {"connected": True, "topics": {}},
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
        service = self.service(
            mqtt_snapshot=lambda: {
                "topics": {
                    "pump_metrics": {"json": {"valve": "open", "manual_valve": "closed", "valve_current": "0.12"}},
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

        service.scheduler_tick()

        self.assertEqual(calls, ["run_v2", "stop_v2"])

    def pilot_config(self, **overrides):
        config = {
            "mode": "navigator",
            "base_duration_minutes": 60,
            "rain_24h_threshold_mm": 5,
            "forecast_rain_threshold_mm": 5,
            "pop_threshold_percent": 70,
            "heat_threshold_c": 32,
            "heat_correction_percent": 20,
            "cold_threshold_c": 22,
            "cold_correction_percent": -20,
            "soil_moisture_enabled": True,
            "soil_sensor_topic_base": "zigbee/0xa4c13844a0908898",
            "soil_wet_skip_threshold_percent": 85,
            "soil_dry_threshold_percent": 45,
            "soil_dry_correction_percent": 15,
            "soil_sample_max_age_hours": 12,
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

    def test_pilot_ignores_stale_garden_soil_sample(self):
        service = self.service()
        service.fetch_pilot_config = lambda: self.pilot_config()
        service.fetch_pilot_base_schedule = lambda: None
        service.build_weather_snapshot = lambda topic: self.pilot_snapshot(soil_moisture=90, soil_age_hours=13)

        decision = service.evaluate_pilot(base_duration=60)

        self.assertEqual(decision["final_duration"], 60)
        self.assertEqual(decision["triggered_rules"], [])
        self.assertFalse(decision["details"]["inputs"]["SoilMoistureUsable"])


if __name__ == "__main__":
    unittest.main()
