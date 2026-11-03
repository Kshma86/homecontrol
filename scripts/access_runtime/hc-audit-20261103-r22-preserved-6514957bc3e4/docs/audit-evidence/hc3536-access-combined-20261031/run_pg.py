import json,unittest
r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_process_binding_postgres'))
v=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),transaction_pooler=True)
print(json.dumps(v));raise SystemExit(0 if r.wasSuccessful() and not r.skipped else 1)
