"""Focused HC control/payload regression matrix; no live services are required.

Run inside the candidate backend image with the frozen public test source.
Host ownership/backup integration and PostgreSQL tests have separate profiles.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'infra/backend'))
NAMES = ['health_routes','dependency_audit','startup_service','scheduler_bridge_samples',
         'scheduler_feedback','scheduler_service','mqtt_monitor_service','mqtt_credentials',
         'process_binding_service','climate_window_guard','power_wall_service',
         'combustion_safety_service','combustion_safety_state','combustion_safety_delivery',
         'combustion_opening_events','ai_images','ai_proxy_service','ai_node_power',
         'read_runtime_repair','read_model_cache','context_service_contract','command_service',
         'api_route_modules','robot_service']

if __name__ == '__main__':
    suite=unittest.defaultTestLoader.loadTestsFromNames(['tests.test_'+name for name in NAMES])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'tests':result.testsRun,'failures':len(result.failures),
                      'errors':len(result.errors),'skipped':len(result.skipped),
                      'modules':NAMES}))
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
