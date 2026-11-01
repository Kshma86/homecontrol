import json,unittest
from pathlib import Path
r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_process_binding_postgres'))
s=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped))
Path('/evidence/postgres-results.json').write_text(json.dumps(s,indent=2))
print(json.dumps(s));raise SystemExit(0 if r.wasSuccessful() and not r.skipped else 1)
