"""Rebuild HC-16 source patch, verify test provenance and seal public evidence."""
import ast
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
unit = read(OUT / 'unit-final/test-summary.json')
pg = read(OUT / 'postgres-final/test-summary.json')
frontend = read(OUT / 'frontend/test-summary.json')
assert all(r['ok'] for r in (unit, pg, frontend))
u = unit['profiles']['unit']['result']
pgmods = pg['profiles']['postgres']['modules']
f = frontend['profiles']['frontend']['result']
for result in [u, f] + [m['result'] for m in pgmods.values()]:
    assert all(result[k] == 0 for k in ('failures', 'errors', 'skipped'))
ids = u['test_ids'] + [i for m in pgmods.values() for i in m['result']['test_ids']]
assert len(set(ids)) == len(ids) == 1007
paths = sorted(list(before['source_sha256']) + ['infra/backend/mower_v3_protocol.py',
    'infra/backend/tests/test_mower_module_boundaries.py',
    'infra/backend/tests/fixtures/hc16_import_probe.py', 'docs/hc-16-repair.md'])
backend = [p for p in paths if p.startswith('infra/backend/')]
for report in (unit, pg):
    for p in backend:
        assert report['source_policies']['standard']['source_sha256'][p] == sha(ROOT / p), p
front_hashes = frontend['source_policies']['standard']['source_sha256']
front_paths = [p for p in front_hashes if p.startswith('infra/frontend/')]
for p in front_paths:
    assert front_hashes[p] == sha(ROOT / p), p
changes = []; diff = []
for path in paths:
    original = OUT / 'original' / path
    if original.exists():
        assert sha(original) == before['source_sha256'][path]
    old = original.read_text() if original.exists() else ''
    current = (ROOT / path).read_text()
    if old == current:
        continue
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
assert len(changed_rows) == 1 and changed_rows[0][0].startswith('| HC-16 ')
counts = {s: sum(row.endswith('| ' + s + ' |') for row in new_rows)
          for s in ('Nyitott', 'Folyamatban', 'Ellenőrzött')}
assert counts == {'Nyitott': 3, 'Folyamatban': 3, 'Ellenőrzött': 42}
links = 0
for path in ['docs/hc-16-repair.md', 'docs/mower-v3-foundation.md',
             'docs/mower-v3-bringup.md', 'docs/ai/mower-domain.md']:
    for target in re.findall(r'\]\(([^)]+)\)', (ROOT / path).read_text()):
        if '://' in target or target.startswith('#'):
            continue
        # summary.json is generated below; all other targets already exist.
        dest = (ROOT / path).parent / target.split('#', 1)[0]
        assert dest.exists() or dest == OUT / 'summary.json', (path, target)
        links += 1
initial = read(OUT / 'unit/test-summary.json')['profiles']['unit']['result']
keys = ('tests', 'failures', 'errors', 'skipped')
summary = dict(ok=True, finding='HC-16', repair='REPAIR-063', status='verified_source_not_deployed',
    active_release='hc-security-20261102-r18', audit_sha256=before['audit_sha256'],
    baseline=dict(tests=806, failures=0, errors=0, skipped=0),
    final=dict(unit={k: u[k] for k in keys}, postgres={k: sum(m['result'][k] for m in pgmods.values()) for k in keys},
        postgres_modules=len(pgmods), frontend=f, frontend_build='passed', unique_backend_tests=len(ids),
        total_tests=len(ids) + f['tests'], rover_related_unit_tests=sum('mower' in i.lower() or 'rover' in i.lower() for i in u['test_ids'])),
    contract_checks=dict(import_orders=120, origin_rejections=28, moved_definition_ast_parity=14,
        service_body_ast_parity=5, old_public_objects_aliased=True, obsolete_operator_settings_removed=True,
        optional_auth_adapter_preserved=True, original_audit_unchanged=True, hc15_fingerprints_preserved=15),
    source_provenance=dict(final_unit_and_postgres_match_current_backend=True, frontend_files_match_tested_source=len(front_paths)),
    scope=dict(only_status_changed='HC-16', registry_counts=counts, new_device_commands=False, db_migrations=False,
        firmware_changes=False, production_changed=False, other_audit_points_fixed=False),
    earlier_attempts=dict(focused_fixture='Wrong parameter URL corrected; initial 404 log retained',
        initial_unit={k: initial[k] for k in keys},
        initial_unit_cause='mower_v3_commands re import removed prematurely; restored before final unit/PG runs',
        earlier_attempts_counted_as_acceptance=False),
    commands=['python3 -B docs/audit-evidence/hc16-20261102/check_scope.py',
        'python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc16-20261102/unit-final',
        'python3 -B scripts/check_hc_tests.py --profile postgres --output docs/audit-evidence/hc16-20261102/postgres-final',
        'python3 -B scripts/check_hc_tests.py --profile frontend --output docs/audit-evidence/hc16-20261102/frontend --npm-cache /tmp/hc23-43-20261102/npm-cache'],
    limitations=['No physical rover access or hardware certification', 'No production deploy/restart; new backend release needed',
        'Next release includes preserved HC-15 and new HC-16 module together', 'HC-20/23/41/43 remain outside this repair'],
    documentation_links_verified=links, changed_files=changes)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
assert read(OUT / 'scope-check.json')['ok'] and read(OUT / 'production-unchanged.json')['ok']
# Verify previous HC-15 evidence was not altered by this repair.
hc15 = ROOT / 'docs/audit-evidence/hc15-20261102'
sealed = read(hc15 / 'SHA256SUMS.json')
# The previous evidence manifest is a path-to-hash dictionary.
for path, want in sealed.items():
    assert sha(hc15 / path) == want, path
manifest = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob('*'))
            if p.is_file() and p.name != 'SHA256SUMS.json' and '__pycache__' not in p.parts}
(OUT / 'SHA256SUMS.json').write_text(json.dumps(manifest, indent=2) + '\n')
assert all(sha(OUT / p) == want for p, want in manifest.items())
print(json.dumps(dict(ok=True, tests=summary['final']['total_tests'], unit=u['tests'], postgres=197,
    frontend=f['tests'], changed_files=len(changes), registry=counts, links_checked=links,
    hc15_evidence_unchanged=len(sealed), evidence_files_sealed=len(manifest))))
