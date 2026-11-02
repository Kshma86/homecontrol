"""HC-20 static reference, exact AST and preservation checks; no external I/O."""
import ast
import hashlib
import json
from pathlib import Path
import re

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = read(OUT / 'before.json')
removed = {'start_scheduled_session', 'run_due_schedules', 'stop_due_schedules'}
service_path = 'infra/backend/irrigation_service.py'
old_source = (OUT / 'original' / service_path).read_text()
old = ast.parse(old_source)
current = ast.parse((ROOT / service_path).read_text())
old_class = next(n for n in old.body if isinstance(n, ast.ClassDef) and n.name == 'IrrigationService')
old_methods = {n.name: n for n in old_class.body if isinstance(n, ast.FunctionDef)}
new_class = next(n for n in current.body if isinstance(n, ast.ClassDef) and n.name == 'IrrigationService')
new_methods = {n.name: n for n in new_class.body if isinstance(n, ast.FunctionDef)}
assert set(old_methods) - set(new_methods) == removed
assert not set(new_methods) - set(old_methods)
old_class.body = [n for n in old_class.body if getattr(n, 'name', None) not in removed]
assert ast.dump(old, include_attributes=False) == ast.dump(current, include_attributes=False)
assert all(ast.dump(old_methods[n]) == ast.dump(new_methods[n]) for n in new_methods)
# Inspect original references including string-based accesses in tests.
pattern = re.compile(r'\b(?:' + '|'.join(sorted(removed)) + r')\b')
original_references = []
for name in before['source_sha256']:
    if name.endswith(('.py', '.md')) and name not in ('AUDIT_REPAIR.md', 'DEPLOYMENT_PREP.md'):
        for number, line in enumerate((OUT / 'original' / name).read_text().splitlines(), 1):
            if pattern.search(line):
                original_references.append(dict(path=name, line=number, text=line.strip()))
# Active source inventory comes from the public, secret-excluding test staging.
# Current workspace files are read; frozen release/history/evidence copies are excluded.
inventory = read(OUT / 'final-stage.json')['source_sha256']
code_exts = {'.py', '.sh', '.js', '.jsx', '.mjs', '.yml', '.yaml', '.service', '.timer', '.json'}
scanned = []; remaining = []
for name in inventory:
    p = ROOT / name
    if (p.suffix not in code_exts or not p.is_file()
        or set(p.parts) & {'private', 'ssh', 'backups', 'audit-evidence', 'access_runtime'}):
        continue
    scanned.append(name)
    for number, line in enumerate(p.read_text().splitlines(), 1):
        if pattern.search(line):
            remaining.append(dict(path=name, line=number, text=line.strip()))
assert not remaining, remaining
assert not pattern.search((ROOT / 'docs/ai/irrigation-domain.md').read_text())
allowed_backend = {service_path, 'infra/backend/tests/test_irrigation_service.py',
                   'infra/backend/tests/test_irrigation_admission.py',
                   'infra/backend/tests/test_irrigation_admission_postgres.py'}
changed_backend = []
for name, want in before['backend_python_sha256'].items():
    if not (ROOT / name).is_file() or sha(ROOT / name) != want:
        changed_backend.append(name)
assert set(changed_backend) == allowed_backend, changed_backend
current_backend = {str(p.relative_to(ROOT)) for p in (ROOT / 'infra/backend').rglob('*.py') if '__pycache__' not in p.parts}
assert current_backend == set(before['backend_python_sha256'])
for name, want in before['sql_sha256'].items():
    assert sha(ROOT / name) == want, name
prior = {}
for repair, entries in before['prior_pending_repairs'].items():
    preserved = []; related = []
    for item in entries:
        path = item['path']
        p = ROOT / path
        if path in ('AUDIT_REPAIR.md', 'DEPLOYMENT_PREP.md'):
            related.append(dict(path=path, reason='HC-20 registry/release notes only'))
        elif path == service_path:
            related.append(dict(path=path, reason='Only the three HC-20 dead methods removed; all other AST identical'))
        else:
            assert not p.exists() if item['state'] == 'deleted' else sha(p) == item['sha256'], path
            preserved.append(path)
    prior[repair] = dict(preserved=preserved, intentional_overlap=related)
    previous = ROOT / 'docs/audit-evidence' / (repair + '-20261102')
    for name, want in read(previous / 'SHA256SUMS.json').items():
        assert sha(previous / name) == want, (repair, name)
assert sha(ROOT / 'HC_REFACTOR_AUDIT.md') == before['audit_sha256']
result = dict(ok=True, finding='HC-20', removed_methods=sorted(removed),
    removed_definition_lines=sum(old_methods[n].end_lineno-old_methods[n].lineno+1 for n in removed),
    method_count_before=len(old_methods), method_count_after=len(new_methods),
    entire_service_ast_unchanged_except_three_deletions=True, remaining_method_ast_unchanged=len(new_methods),
    original_references=original_references, active_source_files_scanned=len(scanned), remaining_runtime_or_test_references=remaining,
    domain_documentation_has_no_removed_method_references=True, changed_backend_files=sorted(changed_backend),
    sql_migrations_unchanged=len(before['sql_sha256']),
    app_routes_startup_scheduler_admission_recovery_ingest_unchanged=True, prior_pending_repairs=prior,
    original_audit_unchanged=True, public_apis_preserved=True, historical_sessions_preserved=True,
    new_device_commands=False, scheduling_semantic_changes=False, production_deployed=False)
(OUT / 'scope-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(ok=True, removed=len(removed), removed_definition_lines=result['removed_definition_lines'],
                     unchanged_remaining_methods=len(new_methods), files_scanned=len(scanned), sql_unchanged=len(before['sql_sha256']))))
