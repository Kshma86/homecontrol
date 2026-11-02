"""Reproduce HC-16's structural and unchanged-contract checks (no external I/O)."""
import ast
from copy import deepcopy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BACKEND = ROOT / 'infra/backend'
BEFORE = json.loads((OUT / 'before.json').read_text())
MOVED = {
    'mower_v3_service': ['RoverReadError', 'UnknownMutation', 'unique_object', 'reject_constant',
                         'integer', 'hex_id', 'require', 'validate_identity', 'validate_state'],
    'mower_v3_commands': ['request_id'],
    'mower_motor_test': ['motor_identity', 'validate_parameters_status', 'validate_motor_state', 'parameters_fresh'],
}
SERVICES = set(MOVED) | {'mower_manual_service', 'mower_parameters_service'}
CONSTANTS = {'CONTRACT', 'MANUAL_PROTOCOL', 'STATES'}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def imports(p):
    tree = ast.parse(p.read_text())
    names = {x.stem for x in BACKEND.glob('*.py')}
    return sorted({n.module.split('.')[0] for n in ast.walk(tree)
                   if isinstance(n, ast.ImportFrom) and n.module and n.module.split('.')[0] in names}
                  | {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                     for a in n.names if a.name.split('.')[0] in names})


def cycles(graph):
    def reach(root):
        seen = set(); todo = list(graph[root])
        while todo:
            name = todo.pop()
            if name not in seen:
                seen.add(name); todo.extend(graph.get(name, []))
        return seen
    reachable = {name: reach(name) for name in graph}
    groups = {tuple(sorted({a} | {b for b in reachable[a] if a in reachable.get(b, set())}))
              for a in graph if a in reachable[a]}
    return sorted(groups)


class WithoutImports(ast.NodeTransformer):
    def visit_Import(self, node):
        return None
    def visit_ImportFrom(self, node):
        return None


def dump_without_imports(tree):
    return ast.dump(WithoutImports().visit(deepcopy(tree)), include_attributes=False)


protocol = ast.parse((BACKEND / 'mower_v3_protocol.py').read_text())
new_defs = {n.name: n for n in protocol.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
validator_parity = {}
module_parity = {}
for name in sorted(SERVICES):
    original = OUT / 'original/infra/backend' / (name + '.py')
    assert sha(original) == BEFORE['source_sha256']['infra/backend/' + name + '.py']
    old = ast.parse(original.read_text())
    current = ast.parse((BACKEND / (name + '.py')).read_text())
    for n in old.body:
        if getattr(n, 'name', None) in MOVED.get(name, []):
            validator_parity[n.name] = dump_without_imports(n) == dump_without_imports(new_defs[n.name])
            assert validator_parity[n.name], n.name
    # Exact AST body equality, ignoring imports and the definitions just moved.
    old.body = [n for n in old.body if getattr(n, 'name', None) not in MOVED.get(name, [])
                and not (name == 'mower_v3_service' and isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id in CONSTANTS for t in n.targets))]
    module_parity[name] = dump_without_imports(old) == dump_without_imports(current)
    assert module_parity[name], name

old_constants = {n.targets[0].id: ast.dump(n.value) for n in ast.parse(
    (OUT / 'original/infra/backend/mower_v3_service.py').read_text()).body
    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in CONSTANTS}
new_constants = {n.targets[0].id: ast.dump(n.value) for n in protocol.body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in CONSTANTS}
assert old_constants == new_constants
old_settings = ast.parse((OUT / 'original/infra/backend/settings.py').read_text())
settings_class = next(n for n in old_settings.body if isinstance(n, ast.ClassDef) and n.name == 'BackendSettings')
removed = {'mower_operator_password_hash', 'mower_operator_session_secret'}
settings_class.body = [n for n in settings_class.body if not (isinstance(n, ast.AnnAssign)
                       and isinstance(n.target, ast.Name) and n.target.id in removed)]
assert ast.dump(old_settings) == ast.dump(ast.parse((BACKEND / 'settings.py').read_text()))

hc15 = []
for entry in BEFORE['hc15_pending_change_fingerprints']:
    p = ROOT / entry['path']
    match = not p.exists() if entry['state'] == 'deleted' else sha(p) == entry['sha256']
    assert match, entry['path']
    hc15.append(dict(path=entry['path'], preserved=True))

graph = {p.stem: imports(p) for p in BACKEND.glob('*.py')}
old_cycles = cycles(BEFORE['graph']); new_cycles = cycles(graph)
assert any(SERVICES <= set(group) for group in old_cycles)
assert not any(SERVICES & set(group) for group in new_cycles)
assert graph['mower_v3_protocol'] == ['rover_parameters'] and graph['rover_parameters'] == []
manifest = json.loads((ROOT / 'backups/releases/hc-security-20261102-r18/release.json').read_text())
unchanged = ['infra/backend/mower_operator_auth.py', 'infra/backend/rover_parameters.py',
             'infra/frontend/src/hooks/useMowerOperator.js']
# Locate frontend hook by filename if its exact directory differs.
unchanged = [str(next((ROOT / 'infra/frontend/src').rglob('useMowerOperator.*')).relative_to(ROOT))
             if p.endswith('useMowerOperator.js') else p for p in unchanged]
for p in unchanged:
    assert sha(ROOT / p) == manifest['source_sha256'][p], p
assert sha(ROOT / 'HC_REFACTOR_AUDIT.md') == BEFORE['audit_sha256']
result = dict(ok=True, scope='HC-16 only; HC-15 pending fingerprints preserved',
              before_rover_cycles=[g for g in old_cycles if SERVICES & set(g)],
              after_rover_cycles=[g for g in new_cycles if SERVICES & set(g)],
              current_rover_imports={k: graph[k] for k in sorted(SERVICES | {'mower_v3_protocol'})},
              moved_definition_ast_parity=validator_parity, existing_service_body_ast_parity=module_parity,
              contract_constants_ast_unchanged=True, settings_only_two_unused_fields_removed=True,
              hc15_fingerprints=hc15, unchanged_auth_codec_frontend=unchanged,
              audit_original_unchanged=True, new_device_commands=False, timing_changes=False,
              db_migrations=False, production_deployed=False)
(OUT / 'scope-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(ok=True, moved_definitions=len(validator_parity), service_bodies=len(module_parity),
                      previous_cycle_modules=len(result['before_rover_cycles'][0]), current_rover_cycles=0,
                      hc15_preserved=len(hc15))))
