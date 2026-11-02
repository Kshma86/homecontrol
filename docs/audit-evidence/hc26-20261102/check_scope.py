"""HC-26 source boundary and previous repair preservation, without network I/O."""
import ast
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = read(OUT / 'before.json')
path = 'apps/ha-growatt-poller/ha_growatt_poller.py'
old_tree = ast.parse((OUT / 'original' / path).read_text())
new_tree = ast.parse((ROOT / path).read_text())
functions = lambda tree: {n.name:n for n in tree.body if isinstance(n, ast.FunctionDef)}
old_funcs, new_funcs = functions(old_tree), functions(new_tree)
assert set(old_funcs)-set(new_funcs) == {'ha_get_state'}
assert set(new_funcs)-set(old_funcs) == {'ha_get_states','ha_state_age','build_payload','poll_payload'}
unchanged = [name for name in old_funcs if name in new_funcs and name != 'main']
for name in unchanged:
    assert ast.dump(old_funcs[name]) == ast.dump(new_funcs[name]), name
old_assigns = [ast.dump(n) for n in old_tree.body if isinstance(n, (ast.Assign, ast.Import, ast.ImportFrom))]
new_assigns = [ast.dump(n) for n in new_tree.body if isinstance(n, (ast.Assign, ast.Import, ast.ImportFrom))]
assert old_assigns == new_assigns  # Config, metric map, dependencies and defaults unchanged.
old_connect = next(n for n in ast.walk(old_funcs['main']) if isinstance(n, ast.FunctionDef) and n.name=='on_connect')
new_connect = next(n for n in ast.walk(new_funcs['main']) if isinstance(n, ast.FunctionDef) and n.name=='on_connect')
assert ast.dump(old_connect) == ast.dump(new_connect)
for name, want in {**before['backend_sha256'], **before['sql_sha256']}.items():
    assert sha(ROOT / name)==want, name
assert {str(p.relative_to(ROOT)) for p in (ROOT/'infra/backend').rglob('*.py') if '__pycache__' not in p.parts} == set(before['backend_sha256'])
supporting_changed = []
for name, want in before['supporting_sha256'].items():
    if sha(ROOT/name)!=want: supporting_changed.append(name)
assert supporting_changed == [path], supporting_changed
latest = {}
for repair, entries in before['prior_pending_repairs'].items():
    for e in entries: latest[e['path']] = e
    d=ROOT/'docs/audit-evidence'/(repair+'-20261102')
    for name, want in read(d/'SHA256SUMS.json').items(): assert sha(d/name)==want,(repair,name)
intentional = {'AUDIT_REPAIR.md','DEPLOYMENT_PREP.md','scripts/check_hc_tests.py','scripts/hc_test_suite.py'}
preserved = []
for name, entry in latest.items():
    if name in intentional: continue
    assert not (ROOT/name).exists() if entry['state']=='deleted' else sha(ROOT/name)==entry['sha256'],name
    preserved.append(name)
old = (OUT/'original/scripts/check_hc_tests.py').read_text()
expected = old.replace("'x10','mdns')", "'x10','mdns','growatt')",1)
expected = expected.replace("profile in ('deployed','ownership','mdns')", "profile in ('deployed','ownership','mdns','growatt')",1)
expected = expected.replace("profile in ('unit','ownership','deployed','mdns')", "profile in ('unit','ownership','deployed','mdns','growatt')",1)
expected = expected.replace("selected=image('homecontrol-mdns') if profile=='mdns' else backend", "selected=image({'mdns':'homecontrol-mdns','growatt':'homecontrol-ha-growatt-poller'}[profile]) if profile in ('mdns','growatt') else backend",1)
assert (ROOT/'scripts/check_hc_tests.py').read_text()==expected
old = (OUT/'original/scripts/hc_test_suite.py').read_text()
expected = old.replace("choices=('unit', 'ownership', 'postgres', 'deployed', 'mdns')", "choices=('unit', 'ownership', 'postgres', 'deployed', 'mdns', 'growatt')",1)
expected = expected.replace("    elif args.profile == 'ownership':", "    elif args.profile == 'growatt':\n        sys.path.insert(0, str(ROOT/'apps/ha-growatt-poller'))\n        suite = loader.discover(str(ROOT/'apps/ha-growatt-poller/tests'))\n    elif args.profile == 'ownership':",1)
assert (ROOT/'scripts/hc_test_suite.py').read_text()==expected
assert sha(ROOT/'HC_REFACTOR_AUDIT.md')==before['audit_sha256']
measurement=read(OUT/'live-measurement.json');smoke=read(OUT/'live-candidate-smoke.json')
assert measurement['ok'] and smoke['ok'] and read(OUT/'usage.json')['enabled_and_running']
assert measurement['batch_median_seconds'] < measurement['individual_median_seconds']
assert all(r['batch']['get_requests']==1 and r['individual']['get_requests']==27 for r in measurement['rounds'])
assert smoke['get_count']==1 and smoke['per_metric_age_fields']==smoke['published_metric_count']
assert smoke['mqtt_publish_commands']==smoke['ha_mutation_commands']==0
compat=read(OUT/'payload-compatibility.json')
assert compat['ok'] and len(compat['scenarios'])==4
result=dict(ok=True,finding='HC-26',usage_verified=True,measured_batch_benefit=True,
    request_count_before=27,request_count_after=1,unchanged_poller_functions=unchanged,
    config_metric_map_imports_and_defaults_ast_unchanged=True,on_connect_ast_unchanged=True,
    backend_python_unchanged=len(before['backend_sha256']),sql_migrations_unchanged=len(before['sql_sha256']),
    worker_health_mqtt_credentials_requirements_and_dockerfile_unchanged=True,ingest_source_unchanged=True,mdns_source_and_tests_unchanged=True,
    prior_pending_paths_preserved=preserved,intentional_harness_and_registry_overlap=sorted(intentional),
    prior_evidence_unchanged=True,original_audit_unchanged=True,
    original_payload_fields_exactly_preserved_in_four_synthetic_scenarios=True,
    additive_fields=['meta[key].observed_at','meta[key].ha_state_age_seconds'],
    sample_time_semantics='UTC snapshot observation after fetch; not physical acquisition time',
    timeout_semantics='One existing requests timeout; no hard whole-cycle deadline claimed',
    automatic_other_audit_fixes=False,production_deployed=False,live_ha_mutation_commands=0,live_mqtt_publish_commands=0)
(OUT/'scope-check.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(ok=True,backend_unchanged=result['backend_python_unchanged'],sql_unchanged=result['sql_migrations_unchanged'],prior_paths_preserved=len(preserved),wire_scenarios=4)))
