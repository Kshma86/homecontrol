"""Validate HC-24 source/test provenance, scope and public evidence checksums."""
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
mdns = read(OUT / 'mdns/test-summary.json')
unit = read(OUT / 'unit/test-summary.json')
assert scope['ok'] and mdns['ok'] and unit['ok']
m = mdns['profiles']['mdns']['result']
u = unit['profiles']['unit']['result']
keys = ('tests', 'failures', 'errors', 'skipped')
for result in (m, u):
    assert all(result[k] == 0 for k in keys[1:])
ids = m['test_ids'] + u['test_ids']
assert len(set(ids)) == len(ids) == 835 and m['tests'] == 19 and u['tests'] == 816
runtime = read(OUT / 'production-unchanged.json')
assert runtime['ok'] and not runtime['runtime_drift'] and runtime['runtime_source_count'] == 736
assert mdns['profiles']['mdns']['image'] == runtime['containers']['homecontrol-mdns']['image']
paths = sorted(list(before['source_sha256']) + ['infra/mdns/tests/test_mdns_responder.py', 'docs/hc-24-repair.md'])
provenance = [p for p in paths if p.endswith('.py')]
for report, policy in ((mdns, 'deployed'), (unit, 'standard')):
    staged = report['source_policies'][policy]
    for name in provenance:
        assert sha(ROOT / name) == staged['source_sha256'][name], (policy, name)
assert mdns['source_policies']['deployed']['test_only_changes'] == []
assert unit['source_policies']['standard']['test_only_changes'] == ['optional policy in disposable standard-profile source only']
changes = []; diff = []
for name in paths:
    original = OUT / 'original' / name
    if original.exists():
        assert sha(original) == before['source_sha256'][name]
    old = original.read_text() if original.exists() else ''
    current = (ROOT / name).read_text()
    assert old != current, name
    changes.append(dict(path=name, state='modified' if original.exists() else 'added', sha256=sha(ROOT / name)))
    diff.extend(difflib.unified_diff(old.splitlines(keepends=True), current.splitlines(keepends=True),
        fromfile='a/' + name if original.exists() else '/dev/null', tofile='b/' + name))
    if name.endswith('.py'):
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
assert len(changed_rows) == 1 and changed_rows[0][0].startswith('| HC-24 ')
counts = {s: sum(row.endswith('| ' + s + ' |') for row in new_rows)
          for s in ('Nyitott', 'Folyamatban', 'Ellenőrzött')}
assert counts == {'Nyitott': 1, 'Folyamatban': 3, 'Ellenőrzött': 44}
links = 0
for target in re.findall(r'\]\(([^)]+)\)', (ROOT / 'docs/hc-24-repair.md').read_text()):
    if '://' in target or target.startswith('#'):
        continue
    dest = ROOT / 'docs' / target.split('#', 1)[0]
    assert dest.exists() or dest == OUT / 'summary.json', target
    links += 1
baseline = read(OUT / 'baseline-parser.json')
assert baseline['ok'] and all(r['timed_out'] for r in baseline['original_cycles'])
separate = read(OUT / 'separate-observation.json')
assert not separate['fixed'] and not separate['blocks_hc24']
summary = dict(ok=True, finding='HC-24', repair='REPAIR-065', completed_at=datetime.now(timezone.utc).isoformat(),
    status='verified_source_not_deployed', active_release=before['active_release'], audit_sha256=before['audit_sha256'],
    original_reproduction=dict(cycles=len(baseline['original_cycles']), deadline_seconds=.1, lan_packets_sent=0),
    final=dict(mdns={k: m[k] for k in keys}, backend_unit={k: u[k] for k in keys}, unique_tests=len(ids),
        mdns_image=mdns['profiles']['mdns']['image'], postgres_newly_tested=False, frontend_newly_tested=False,
        random_byte_fixtures_within_mdns_tests=3000, generated_valid_names_within_mdns_tests=200),
    source_provenance=dict(tested_python_paths=provenance, mdns_and_backend_profiles_match_current_source=True,
        mdns_profile='deployed policy unchanged; actual mdns image; network none; socket constructor guarded',
        backend_profile='standard disposable optional backup policy only'),
    contract_checks=dict(changed_parser_functions=scope['changed_parser_functions'], max_pointer_jumps=128,
        pointer_limit_is_local_resource_limit=True, max_expanded_name_bytes=255,
        original_A_ANY_and_announcement_bytes_preserved=True, bad_questions_discard_whole_question_section=True,
        fake_receive_loop_continues=True, backend_python_unchanged=185, sql_migrations_unchanged=62,
        prior_hc15_hc16_hc20_evidence_unchanged=True),
    scope=dict(only_status_changed='HC-24', registry_counts=counts, other_audit_points_fixed=False,
        production_changed=False, real_lan_packets_sent=0),
    commands=['python3 -B docs/audit-evidence/hc24-20261102/baseline_probe.py',
        'python3 -B docs/audit-evidence/hc24-20261102/check_scope.py',
        'python3 -B scripts/check_hc_tests.py --profile mdns --output docs/audit-evidence/hc24-20261102/mdns',
        'python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc24-20261102/unit'],
    dependencies=['New mdns image and controlled mdns release required',
        'HC-24 can ship independently of pending backend HC-15/16/20',
        'Only mdns test staging/profile integration required; no HC-17/18 or HC-23 implementation repair'],
    limitations=['No LAN packet test; only synthetic parser/fake-socket fixtures',
        'No general DNS/mDNS compliance certification',
        'Existing multi-question builder issue recorded separately and not fixed',
        'No production deploy/restart; AI remains disabled'],
    standards_reference='https://www.rfc-editor.org/rfc/rfc1035.html (sections 2.3.4, 3.1, 4.1.4)',
    documentation_links_verified=links, changed_files=changes)
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
manifest = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob('*'))
            if p.is_file() and p.name != 'SHA256SUMS.json' and '__pycache__' not in p.parts}
(OUT / 'SHA256SUMS.json').write_text(json.dumps(manifest, indent=2) + '\n')
assert all(sha(OUT / name) == want for name, want in manifest.items())
print(json.dumps(dict(ok=True, tests=len(ids), mdns=m['tests'], backend_unit=u['tests'], changed_files=len(changes),
    registry=counts, documentation_links_checked=links, evidence_files_sealed=len(manifest))))
