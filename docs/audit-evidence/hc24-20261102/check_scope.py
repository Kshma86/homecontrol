"""HC-24 parser scope, baseline compatibility and previous repair preservation."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = read(OUT / 'before.json')
source_path = 'infra/mdns/mdns_responder.py'
old_tree = ast.parse((OUT / 'original' / source_path).read_text())
new_tree = ast.parse((ROOT / source_path).read_text())
old_functions = {n.name: n for n in old_tree.body if isinstance(n, ast.FunctionDef)}
new_functions = {n.name: n for n in new_tree.body if isinstance(n, ast.FunctionDef)}
assert old_functions.keys() == new_functions.keys()
changed = [name for name in old_functions if ast.dump(old_functions[name]) != ast.dump(new_functions[name])]
assert changed == ['read_name', 'parse_questions'], changed
for name, want in before['backend_sha256'].items():
    assert sha(ROOT / name) == want, name
assert {str(p.relative_to(ROOT)) for p in (ROOT / 'infra/backend').rglob('*.py') if '__pycache__' not in p.parts} == set(before['backend_sha256'])
for name, want in before['sql_sha256'].items():
    assert sha(ROOT / name) == want, name
# Later completed repairs intentionally supersede some earlier fingerprints.
latest = {}
for repair, entries in before['prior_pending_repairs'].items():
    for e in entries:
        latest[e['path']] = e
    previous = ROOT / 'docs/audit-evidence' / (repair + '-20261102')
    for name, want in read(previous / 'SHA256SUMS.json').items():
        assert sha(previous / name) == want, (repair, name)
intentional = {'AUDIT_REPAIR.md', 'DEPLOYMENT_PREP.md', 'scripts/stage_hc_test_source.py', 'scripts/check_hc_tests.py'}
preserved = []
for name, entry in latest.items():
    if name in intentional:
        continue
    assert not (ROOT / name).exists() if entry['state'] == 'deleted' else sha(ROOT / name) == entry['sha256'], name
    preserved.append(name)
# Verify the two old staging-harness files changed only for mDNS participation.
old_stage = (OUT / 'original/scripts/stage_hc_test_source.py').read_text()
assert (ROOT / 'scripts/stage_hc_test_source.py').read_text() == old_stage.replace(
    "FOLDERS = ('infra/backend', 'apps/bridge_runtime'", "FOLDERS = ('infra/backend', 'infra/mdns', 'apps/bridge_runtime'", 1)
old_harness = (OUT / 'original/scripts/check_hc_tests.py').read_text()
expected = old_harness.replace("'ingest','x10')", "'ingest','x10','mdns')", 1)
expected = expected.replace("profile in ('deployed','ownership')", "profile in ('deployed','ownership','mdns')", 1)
expected = expected.replace("profile in ('unit','ownership','deployed')", "profile in ('unit','ownership','deployed','mdns')", 1)
expected = expected.replace("    result=execute(base_run(source,root=profile=='ownership')+[backend,'python','-B','/src/scripts/hc_test_suite.py',profile],out/(profile+'.log'))", "    selected=image('homecontrol-mdns') if profile=='mdns' else backend\n    result=execute(base_run(source,root=profile=='ownership')+[selected,'python','-B','/src/scripts/hc_test_suite.py',profile],out/(profile+'.log'))\n    result['image']=selected", 1)
assert (ROOT / 'scripts/check_hc_tests.py').read_text() == expected
old_suite = (OUT / 'original/scripts/hc_test_suite.py').read_text()
expected_suite = old_suite.replace("choices=('unit', 'ownership', 'postgres', 'deployed')", "choices=('unit', 'ownership', 'postgres', 'deployed', 'mdns')", 1)
expected_suite = expected_suite.replace("    if args.profile == 'ownership':", "    if args.profile == 'mdns':\n        sys.path.insert(0, str(ROOT/'infra/mdns'))\n        suite = loader.discover(str(ROOT/'infra/mdns/tests'))\n    elif args.profile == 'ownership':", 1)
assert (ROOT / 'scripts/hc_test_suite.py').read_text() == expected_suite
assert sha(ROOT / 'HC_REFACTOR_AUDIT.md') == before['audit_sha256']
spec = importlib.util.spec_from_file_location('hc24_current', ROOT / source_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
baseline = read(OUT / 'baseline-parser.json')
with patch.object(module.socket, 'socket', side_effect=AssertionError('LAN forbidden')):
    for q in baseline['valid_queries']:
        packet = bytes.fromhex(q['query_hex'])
        assert [list(v) for v in module.parse_questions(packet)] == q['parsed']
        assert module.should_answer(packet, 'hc.local') == q['should_answer']
        assert module.build_response(packet, 'hc.local', '192.0.2.23').hex() == q['response_hex']
    assert module.build_announcement('hc.local', '192.0.2.23').hex() == baseline['announcement_hex']
    # Record the pre-existing multi-question response issue separately; do not fix it.
    packet = struct.pack('!HHHHHH', 0x1234, 0, 2, 0, 0, 0) + module.encode_name('hc.local') + struct.pack('!HH', 1, 1)
    packet += b'\xc0\x0c' + struct.pack('!HH', 255, 1)
    response = module.build_response(packet, 'hc.local', '192.0.2.23')
    unrelated = dict(question_count_parsed=len(module.parse_questions(packet)),
        response_qdcount=struct.unpack('!H', response[4:6])[0],
        question_bytes_copied=len(response[12:-16]), original_question_bytes=len(packet)-12,
        build_response_ast_unchanged=True, fixed=False, blocks_hc24=False,
        description='Existing builder copies both questions while declaring QDCOUNT=1. Separate protocol issue, outside the HC-24 loop fix.')
    assert unrelated['question_count_parsed'] == 2 and unrelated['response_qdcount'] == 1
    assert unrelated['question_bytes_copied'] == unrelated['original_question_bytes']
(OUT / 'separate-observation.json').write_text(json.dumps(unrelated, indent=2) + '\n')
result = dict(ok=True, finding='HC-24', changed_parser_functions=changed,
    unchanged_parser_functions=[n for n in old_functions if n not in changed],
    changed_constants=['MAX_NAME_BYTES=255', 'MAX_POINTER_JUMPS=128 (local resource limit)'],
    single_question_A_ANY_response_bytes_unchanged=True, announcement_bytes_unchanged=True,
    backend_python_unchanged=len(before['backend_sha256']), sql_migrations_unchanged=len(before['sql_sha256']),
    previous_pending_paths_preserved=preserved, intentional_harness_and_registry_overlap=sorted(intentional),
    prior_evidence_unchanged=True, original_audit_unchanged=True,
    automatic_other_audit_fixes=False, production_changed=False, lan_packets_sent=0,
    separate_multi_question_observation='separate-observation.json')
(OUT / 'scope-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(ok=True, changed_functions=changed, backend_unchanged=result['backend_python_unchanged'],
    sql_unchanged=result['sql_migrations_unchanged'], prior_paths_preserved=len(preserved))))
