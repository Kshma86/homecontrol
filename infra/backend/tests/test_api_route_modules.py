import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context_payload_service import compact_context_payload


class ApiRouteModulesTest(unittest.TestCase):
    def test_compact_context_trims_large_default_sections(self):
        payload = {
            "realtime": {
                "backup": {"backups": [{"name": str(index)} for index in range(8)]},
                "power_wall": {"devices": [{"entity_id": index, "state": {"power_w": index}} for index in range(20)], "recent_measurements": [1]},
                "tuya": {"devices": [{"entity_id": index, "state": {"switch_state": True}} for index in range(20)], "recent_measurements": [1]},
            }
        }

        compact = compact_context_payload(payload)

        self.assertTrue(compact["compact"])
        self.assertEqual(compact["realtime"]["backup"]["backup_count"], 8)
        self.assertEqual(len(compact["realtime"]["backup"]["backups"]), 5)
        self.assertEqual(len(compact["realtime"]["power_wall"]["devices"]), 12)
        self.assertNotIn("recent_measurements", compact["realtime"]["power_wall"])


if __name__ == "__main__":
    unittest.main()
