import json,unittest
from pathlib import Path
names=['mqtt_credentials','host_operations','process_binding_service','read_runtime_repair','ai_proxy_service','ai_images','ai_node_power','read_model_cache','context_service_contract','command_service','api_route_modules','robot_service','scheduler_feedback','scheduler_bridge_samples','scheduler_service','startup_service','admin_bootstrap','schema_service','irrigation_service','irrigation_admission','irrigation_recovery','irrigation_stop_priority','climate_window_guard','power_wall_service','mqtt_monitor_service','deployment_policy','combustion_safety_service','combustion_safety_state','combustion_safety_delivery','combustion_opening_events']
def flatten(suite):
 for test in suite:
  if isinstance(test,unittest.TestSuite):yield from flatten(test)
  else:yield test
items={t.id():t for t in flatten(unittest.defaultTestLoader.loadTestsFromNames(['tests.test_'+n for n in names]))}
r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(items.values()))
summary=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),failed_ids=[t.id() for t,_ in r.failures+r.errors],modules=names)
Path('/evidence/unit-results.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
raise SystemExit(0 if r.wasSuccessful() and not r.skipped else 1)
