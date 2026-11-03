import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from api_route_modules import register_mower_routes
from mower_v3_service import MowerV3Service


class MowerV3RoutesTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        def legacy_unavailable():
            raise AssertionError("v3 must never invoke a legacy service")
        register_mower_routes(app, get_context_service=legacy_unavailable,
                              get_mower_service=legacy_unavailable,
                              get_admin_service=legacy_unavailable, json_ready=lambda data: data,
                              get_mower_v3_service=lambda: MowerV3Service())
        self.client = app.test_client()

    def test_unconfigured_snapshot_is_no_store_and_does_not_touch_legacy(self):
        response = self.client.get("/api/mower/v3/snapshot")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.json["connection"]["status"], "UNCONFIGURED")
        self.assertIsNone(response.json["state"])

    def test_snapshot_registration_does_not_register_mutation_routes(self):
        self.assertEqual(self.client.post("/api/mower/v3/snapshot").status_code, 405)
        self.assertEqual(self.client.post("/api/mower/v3/command").status_code, 404)


if __name__ == "__main__":
    unittest.main()
