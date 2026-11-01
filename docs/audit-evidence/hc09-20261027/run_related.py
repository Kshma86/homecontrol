import json,sys,unittest
from pathlib import Path
sys.path.insert(0,'/audit/infra/backend')
names=['scheduler_feedback','scheduler_feedback_postgres','scheduler_bridge_samples','scheduler_audit_postgres','scheduler_service','startup_service','admin_bootstrap','schema_service',
       'irrigation_service','irrigation_admission','irrigation_admission_postgres','irrigation_recovery',
       'irrigation_recovery_postgres','irrigation_stop_priority','climate_window_guard','power_wall_service',
       'mqtt_monitor_service','deployment_policy','combustion_safety_service','combustion_safety_state',
       'combustion_safety_delivery','combustion_opening_events']
def flatten(suite):
    for test in suite:
        if isinstance(test,unittest.TestSuite):yield from flatten(test)
        else:yield test
items={t.id():t for t in flatten(unittest.defaultTestLoader.loadTestsFromNames(['tests.test_'+n for n in names]))}
r=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(items.values()))
summary=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),failed_ids=[t.id() for t,_ in r.failures+r.errors],modules=names)
Path('/evidence/related-results.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
raise SystemExit(0 if r.wasSuccessful() and not r.skipped else 1)
