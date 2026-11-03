import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from admin_service import AdminService


class AdminBootstrapTest(unittest.TestCase):
    def test_bootstrap_does_not_build_scheduler_audit_data(self):
        service = AdminService.__new__(AdminService)
        service.ensure_opening_schema = Mock()
        service.ensure_temperature_schema = Mock()
        service.fetch_all = Mock(return_value=[])
        service.irrigation_context = Mock(return_value={"live": True})
        service.scheduler_state = Mock(side_effect=AssertionError("expensive scheduler read"))

        payload = service.bootstrap_payload()

        service.scheduler_state.assert_not_called()
        self.assertNotIn("scheduler", payload)
        self.assertEqual(payload["irrigation"], {"live": True})
        self.assertIn("devices", payload)
        self.assertIn("entities", payload)


if __name__ == "__main__":
    unittest.main()
