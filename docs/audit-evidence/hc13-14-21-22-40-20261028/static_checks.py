import ast,hashlib,json
from pathlib import Path
root=Path('/audit');before=Path('/evidence/before')
def funcs(p):
 return {n.name:n for c in ast.parse(p.read_text()).body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef)}
a,b=funcs(before/'infra/backend/irrigation_service.py'),funcs(root/'infra/backend/irrigation_service.py')
keep=['start_solar_pump_batch','stop_solar_pump_batch','solar_pump_scheduler_tick','log_pilot_decision']
assert all(ast.dump(a[n])==ast.dump(b[n]) for n in keep)
old,new=a['evaluate_solar_pump_scheduler'],b['evaluate_solar_pump_scheduler']
old.body=[n for n in old.body if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and n.value.func.attr=='execute_one')]
assert ast.dump(old)==ast.dump(new)
manifest=json.loads(Path('/evidence/before-sha256.json').read_text())
unchanged=[p for p,h in manifest.items() if p.startswith('infra/db/') and hashlib.sha256((root/p).read_bytes()).hexdigest()==h]
all_db=[p for p in manifest if p.startswith('infra/db/')];assert len(unchanged)==len(all_db)
assert hashlib.sha256((root/'HC_REFACTOR_AUDIT.md').read_bytes()).hexdigest()=='51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2'
for prefix in ('infra/backend','apps/ai-server'):
 for p in (root/prefix).rglob('*.py'):ast.parse(p.read_text())
report={'unchanged_irrigation_methods':keep,'decision_formula_unchanged_except_removed_update':True,'unchanged_migration_files':len(unchanged),'audit_unchanged':True,'python_ast':True}
Path('/evidence/static-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
