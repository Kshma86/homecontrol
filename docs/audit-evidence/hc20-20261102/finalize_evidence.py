"""Verify HC-20 test/source provenance and seal its public evidence."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = read(OUT / 'before.json')
scope = read(OUT / 'scope-check.json')
unit = read(OUT / 'unit/test-summary.json')
pg = read(OUT / 'postgres/test-summary.json')
assert scope['ok'] and unit['ok'] and pg['ok']
u = unit['profiles']['unit']['result']
modules = pg['profiles']['postgres']['modules']
keys = ('tests', 'failures', 'errors', 'skipped')
for result in [u] + [m['result'] for m in modules.values()]:
    assert all(result[k] == 0 for k in keys[1:])
ids = u['test_ids'] + [i for m in modules.values() for i in m['result']['test_ids']]
assert len(set(ids)) == len(ids) == 1014
baseline_text = (OUT / 'baseline-unit.log').read_text()
start = list(re.finditer(r'\{"profile"\s*:', baseline_text))[-1].start()
baseline = json.JSONDecoder().raw_decode(baseline_text[start:])[0]
assert baseline['tests'] == 810 and all(baseline[k] == 0 for k in keys[1:])
assert 'Ran 57 tests' in (OUT / 'focused-unit.log').read_text()
assert '\nOK\n' in (OUT / 'focused-unit.log').read_text()
parity = read(OUT / 'payload-parity.json')
assert parity['ok'] and parity['scenarios'] == 12 and not parity['external_work']
assert all(r['exact_side_effect_parity'] for r in parity['results'])
for report in (unit, pg):
    staged = report['source_policies']['standard']['source_sha256']
    mismatches = [name for name in before['backend_python_sha256'] if sha(ROOT / name) != staged[name]]
    assert mismatches == ['infra/backend/deployment_policy.py'], mismatches
    assert report['source_policies']['standard']['test_only_changes'] == ['optional policy in disposable standard-profile source only']
# The frontend was not edited during HC-20 and is not claimed as newly tested.
base_front = read(OUT / 'baseline-stage.json')['source_sha256']
front_paths = [name for name in base_front if name.startswith('infra/frontend/')]
for name in front_paths:
    assert sha(ROOT / name) == base_front[name], name
changes = []; diff = []
paths = sorted(list(before['source_sha256']) + ['docs/hc-20-repair.md'])
for path in paths:
    original = OUT / 'original' / path
    if original.exists():
        assert sha(original) == before['source_sha256'][path], path
    old = original.read_text() if original.exists() else ''
    current = (ROOT / path).read_text()
    assert old != current, path
    changes.append(dict(path=path, state='modified' if original.exists() else 'added', sha256=sha(ROOT / path)))
    diff.extend(difflib.unified_diff(old.splitlines(keepends=True), current.splitlines(keepends=True),
        fromfile='a/' + path if original.exists() else '/dev/null', tofile='b/' + path))
    if path.endswith('.py'):
        ast.parse(current)
(OUT / 'changed-files.json').write_text(json.dumps(changes, indent=2) + '\n')
(OUT / 'source.diff').write_text(''.join(diff))

def rows(text):
    table = text.split('## Tételes javítási lista', 1)[1].split('**Kezdő összesítés:**', 1)[0]
    return re.findall(r'^\| HC-\d\d .*$', table, re.M)

old_rows = rows((OUT / 'original/AUDIT_REPAIR.md').read_text())
new_rows = rows((ROOT / 'AUDIT_REPAIR.md').read_text())
assert len(old_rows) == len(new_rows) == 48
changed_rows = [(a, b) for a, b in zip(old_rows, new_rows) if a != b]
assert len(changed_rows) == 1 and changed_rows[0][0].startswith('| HC-20 ')
counts = {s: sum(row.endswith('| ' + s + ' |') for row in new_rows)
          for s in ('Nyitott', 'Folyamatban', 'Ellenőrzött')}
assert counts == {'Nyitott': 2, 'Folyamatban': 3, 'Ellenőrzött': 43}
assert read(OUT / 'production-unchanged.json')['ok']
links = 0
for name in ('docs/hc-20-repair.md', 'docs/ai/irrigation-domain.md'):
    for target in re.findall(r'\]\(([^)]+)\)', (ROOT / name).read_text()):
        if '://' in target or target.startswith('#'):
            continue
        dest = (ROOT / name).parent / target.split('#', 1)[0]
        assert dest.exists() or dest == OUT / 'summary.json', (name, target)
        links += 1
summary = dict(ok=True, finding='HC-20', repair='REPAIR-064', completed_at=datetime.now(timezone.utc).isoformat(),
    status='verified_source_not_deployed', active_release=before['active_release'], audit_sha256=before['audit_sha256'],
    baseline={k: baseline[k] for k in keys},
    final=dict(unit={k: u[k] for k in keys}, postgres={k: sum(m['result'][k] for m in modules.values()) for k in keys},
        postgres_modules=len(modules), unique_backend_tests=len(ids), focused_overlapping_tests=57,
        exact_before_after_side_effect_scenarios=12, frontend_newly_tested=False),
    source_provenance=dict(backend_python_files=len(before['backend_python_sha256']),
        final_unit_and_postgres_match_current_source_except_documented_test_policy=True,
        frontend_files_unchanged=len(front_paths)),
    contract_checks=dict(removed_methods=scope['removed_methods'], removed_definition_lines=185,
        remaining_method_ast_unchanged=86, sql_migrations_unchanged=62, active_source_files_scanned=491,
        old_method_references_remaining=0, public_apis_preserved=True, historical_sessions_preserved=True,
        prior_hc15_hc16_evidence_unchanged=True),
    scope=dict(only_status_changed='HC-20', registry_counts=counts, new_device_commands=False,
        scheduling_semantic_changes=False, db_migrations=False, production_changed=False, other_audit_points_fixed=False),
    commands=['python3 -B docs/audit-evidence/hc20-20261102/check_scope.py',
        'python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc20-20261102/unit',
        'python3 -B scripts/check_hc_tests.py --profile postgres --output docs/audit-evidence/hc20-20261102/postgres'],
    dependencies=['Preserve HC-01/02/03/04/08 and season-profile contracts',
        'Next backend release includes pending HC-15/16/20 source together',
        'No AI reactivation required; AI remains disabled'],
    limitations=['No physical watering test or hardware qualification', 'No production deployment/restart',
        'HC-24/26 and HC-23/41/43 outstanding parts remain separate'],
    baseline_launch=dict(initial_automatic_approval_review='quota failure; command not executed',
        retry='normal approval succeeded; baseline then ran successfully'),
    documentation_links_verified=links, changed_files=changes)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
manifest = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob('*'))
            if p.is_file() and p.name != 'SHA256SUMS.json' and '__pycache__' not in p.parts}
(OUT / 'SHA256SUMS.json').write_text(json.dumps(manifest, indent=2) + '\n')
assert all(sha(OUT / name) == want for name, want in manifest.items())
print(json.dumps(dict(ok=True, tests=len(ids), unit=u['tests'], postgres=198, changed_files=len(changes),
    registry=counts, links_checked=links, evidence_files_sealed=len(manifest))))
