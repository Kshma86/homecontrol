import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("mower_check", Path(__file__).resolve().parents[3]/"scripts/check_mower_v3.py")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class BringupCheckTest(unittest.TestCase):
    def test_native_readiness_is_not_update_finish_physical_stop_or_qualification(self):
        report = module.bringup_checklist({"configured": True, "read_only": True,
            "connection": {"status": "BRINGUP_CONNECTED"}, "freshness": {"fresh": True},
            "identity": {"mode": "HC_BRINGUP", "motion_permitted": False, "commissioned": False, "token": "hidden"},
            "state": {"state": "DISARMED", "stopped": False, "source_seq": 18, "control_epoch": 1},
            "update": {"locked": True, "error": "METADATA_ERROR", "can_finish": False}})
        self.assertTrue(report["stm_fresh"])
        self.assertEqual(report["source_seq"], 18)
        self.assertEqual(report["update_error"], "METADATA_ERROR")
        self.assertFalse(report["physical_stop_proven"])
        self.assertFalse(report["can_finish"])
        self.assertFalse(report["hardware_qualified"])
        self.assertNotIn("hidden", str(report))

    def test_service_readiness_is_not_operational_or_applied_readiness(self):
        report = module.service_checklist({"configured": True,
            "configuration": {"origin_configured": True, "token_configured": True},
            "connection": {"status": "SERVICE_CONNECTED"}, "freshness": {"fresh": True},
            "service": {"mode": "FIRST_INSTALL_SERVICE", "service_abi": 1, "motion_permitted": False,
                        "applied": False, "storage": "STAGED", "revision": 1, "api_token": "hidden"}})
        self.assertTrue(report["stm_fresh"])
        self.assertFalse(report["motion_permitted"])
        self.assertFalse(report["applied"])
        self.assertEqual(report["mutations_sent"], 0)
        self.assertNotIn("hidden", str(report))

    def test_missing_setup_is_reported_without_inventing_readiness_or_secrets(self):
        report = module.checklist({"configured":False}, {"configured":False}, {"releases":[]})
        self.assertFalse(report["hc_rover_configured"]); self.assertFalse(report["ordinary_stm_fresh"])
        self.assertIsNone(report["native_update_locked"]); self.assertEqual(report["mutations_sent"],0)
        self.assertFalse(report["hardware_qualified"])

    def test_advertisement_does_not_imply_ordinary_readiness_or_hardware_acceptance(self):
        identity = {"contract":"3.1.0","stm_remote_update":True,"update_service_abi":2,"stm_flash_layout":"H743_1M_QSPI2",
                    "stm_image_max_bytes":524288,"profile_crc":"AABBCCDD","stm_confirmed_slot":None,"stm_inactive_slot":None,
                    "compatible":False,"update_locked":True,"secret":"do-not-print"}
        result=module.checklist({"configured":True,"identity":identity},{"configured":True},{"releases":[{}]})
        self.assertTrue(result["vg_updater_advertised"]);self.assertFalse(result["operational_contract_compatible"])
        self.assertFalse(result["hardware_qualified"]);self.assertNotIn("do-not-print",str(result))


if __name__ == "__main__":unittest.main()
