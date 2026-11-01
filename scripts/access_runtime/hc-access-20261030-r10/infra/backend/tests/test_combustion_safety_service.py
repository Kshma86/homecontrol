import unittest
from pathlib import Path
import sys
import time
from copy import deepcopy
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from combustion_safety_service import CombustionSafetyService


class MemoryRuntimeStore:
    def __init__(self):
        self.row = dict(revision=0, latched=False, co_warning_active=False, last_co=None, last_co_sample_at=None)
        self.fail_load = self.fail_save = False
        self.saves = 0

    def load(self):
        if self.fail_load:
            raise RuntimeError('runtime DB unavailable')
        return deepcopy(self.row)

    def save(self, revision, state, *, acknowledge=False):
        if self.fail_save:
            raise RuntimeError('runtime commit failed')
        if revision != self.row['revision']:
            raise RuntimeError('runtime revision conflict')
        self.row = dict(deepcopy(state), revision=revision+1)
        self.saves += 1
        return self.load()


class CombustionSafetyServiceTest(unittest.TestCase):
    def setUp(self):
        self.states = {
            1: {"power": 0},
            3: {"carbon_monoxide": False, "carbon_monoxide_value": 0},
            4: {"smoke": False},
        }
        self.openings = [
            {"entity_id": 10, "extractor_air_role": "primary", "contact": False},
            {"entity_id": 11, "extractor_air_role": "secondary", "contact": True},
        ]
        self.published = []
        self.sample_ts = {}
        self.sample_meta = {}
        self.runtime_store = MemoryRuntimeStore()
        self.config = {
            "enabled": True, "fan_on_w": 50, "fan_off_w": 20, "fan_on_seconds": 0, "fan_off_seconds": 0,
            "co_warning_ppm": 10, "co_shutdown_ppm": 20, "co_rise_ppm": 2, "auto_shutdown": True,
            "green_interval_seconds": 60, "secondary_interval_seconds": 20, "closed_interval_seconds": 4, "pulse_seconds": 1,
            "green_brightness": 50, "orange_brightness": 200, "red_brightness": 254,
            "green_color": "#00ff00", "orange_color": "#ff8c00", "red_color": "#ff0000",
        }

        def fetch_all(sql, params=None):
            if "opening_sensor_policy" in sql:
                return [dict(x, ts=x.get('ts', time.time()), meta=x.get('meta', {'retained': False})) for x in self.openings]
            if "combustion_safety_event" in sql:
                return []
            entity_id, keys = params
            return [{"key": key, "v_num": value if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
                     "v_bool": value if isinstance(value, bool) else None,
                     "v_text": value if isinstance(value, str) else None,
                     "v_json": value if isinstance(value, dict) else None,
                     "ts": self.sample_ts.get((entity_id, key), time.time()), "meta": self.sample_meta.get((entity_id, key), {'retained': False})}
                    for key, value in self.states.get(entity_id, {}).items() if key in keys]

        def fetch_one(sql, params=None):
            if "combustion_safety_config" in sql:
                return self.config
            if "topic_base" in sql:
                return {"topic_base": {1: "zigbee/extractor", 2: "zigbee/light"}[params[0]]}
            if "select d.ext_id" in sql:
                return {"ext_id": {2: "indicator", 3: "co"}.get(params[0], "unknown")}
            return None

        self.service = CombustionSafetyService(
            fetch_all, fetch_one, lambda *args: {"id": 1},
            lambda topic, payload: self.published.append((topic, payload)) or (True, "published"),
            lambda key: {"combustion_extractor": 1, "combustion_indicator": 2,
                         "combustion_co_sensor": 3, "combustion_smoke_sensor": 4}[key],
            lambda ext_id: {"radio_online": True, "radio_last_seen_ts": None, "radio_age_hours": 1},
            runtime_store=self.runtime_store,
        )

    def step(self, now):
        with patch('combustion_safety_service.time.time', return_value=now), patch('combustion_safety_service.time.monotonic', return_value=now):
            return self.service.tick()

    def start_fan(self):
        self.states[1]["power"] = 113
        with patch.object(self.service, '_indicator', lambda *a: None):
            CombustionSafetyServiceTest.step(self, 100)
            return CombustionSafetyServiceTest.step(self, 101)

    def test_primary_open_is_green(self):
        snapshot = self.start_fan()
        self.assertTrue(snapshot["fan_active"])
        self.assertEqual(snapshot["level"], "green")

    def test_secondary_and_closed_levels(self):
        self.openings[0]["contact"] = True
        self.openings[1]["contact"] = False
        self.assertEqual(self.start_fan()["level"], "secondary")
        self.openings[1]["contact"] = True
        self.assertEqual(self.step(102)["level"], "closed")

    def test_co_warning_overrides_open_window(self):
        self.start_fan()
        self.states[3]["carbon_monoxide_value"] = 12
        snapshot = self.step(102)
        self.assertEqual(snapshot["level"], "co_warning")
        self.states[3]["carbon_monoxide_value"] = 12
        self.assertEqual(self.step(103)["level"], "co_warning")

    def test_alarm_latches_and_shutdown_is_not_spammed(self):
        self.start_fan()
        self.states[3]["carbon_monoxide"] = True
        self.service.tick()
        self.service.tick()
        off = [item for item in self.published if item == ("zigbee/extractor/set", {"state": "OFF"})]
        self.assertEqual(len(off), 1)
        self.assertTrue(self.service.latched)

    def test_preview_off_cancels_and_uses_indicator_only(self):
        result = self.service.preview_indicator("off")
        self.assertTrue(result["ok"])
        self.assertTrue(result["cancelled_preview"])
        self.assertEqual(self.published[0], ("zigbee/light/set", {"state": "OFF"}))

    def test_indicator_color_conversion(self):
        xy = self.service._hex_to_xy("#ff0000")
        self.assertGreater(xy["x"], 0.6)
        self.assertLess(xy["y"], 0.4)

    def test_indicator_radio_status_is_exposed(self):
        snapshot = self.step(100)
        self.assertTrue(snapshot["indicator"]["configured"])
        self.assertTrue(snapshot["indicator"]["radio_online"])


if __name__ == "__main__":
    unittest.main()
