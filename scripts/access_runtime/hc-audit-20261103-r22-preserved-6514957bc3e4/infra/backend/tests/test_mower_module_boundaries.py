"""HC-16 structural boundary and current single-user API regression."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

BACKEND = Path(__file__).resolve().parents[1]
SERVICES = {'mower_v3_service', 'mower_v3_commands', 'mower_manual_service',
            'mower_motor_test', 'mower_parameters_service'}


def import_graph():
    modules = {p.stem: p for p in BACKEND.glob('*.py')}
    return {name: {n.module.split('.')[0] for n in ast.walk(ast.parse(p.read_text()))
                   if isinstance(n, ast.ImportFrom) and n.module and n.module.split('.')[0] in modules}
            | {a.name.split('.')[0] for n in ast.walk(ast.parse(p.read_text()))
               if isinstance(n, ast.Import) for a in n.names if a.name.split('.')[0] in modules}
            for name, p in modules.items()}


class MowerModuleBoundaryTest(unittest.TestCase):
    def test_service_dependencies_have_no_cycle_including_lazy_imports(self):
        graph = import_graph()
        for root in SERVICES:
            pending = list(graph[root]); visited = set()
            while pending:
                name = pending.pop()
                self.assertNotEqual(name, root, 'Circular rover import: ' + root)
                if name not in visited:
                    visited.add(name); pending.extend(graph[name])

    def test_protocol_has_only_pure_codec_dependency(self):
        graph = import_graph()
        self.assertEqual(graph['mower_v3_protocol'], {'rover_parameters'})
        self.assertEqual(graph['rover_parameters'], set())
        tree = ast.parse((BACKEND / 'mower_v3_protocol.py').read_text())
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(imports, {'re', 'rover_parameters'})

    def test_old_public_paths_reexport_same_contract_objects(self):
        import mower_v3_protocol as protocol
        import mower_v3_service as service
        import mower_v3_commands as commands
        import mower_motor_test as motor
        for name in ('RoverReadError', 'UnknownMutation', 'unique_object', 'reject_constant',
                     'integer', 'hex_id', 'require', 'validate_identity', 'validate_state'):
            self.assertIs(getattr(service, name), getattr(protocol, name))
        self.assertIs(commands.request_id, protocol.request_id)
        for name in ('motor_identity', 'validate_parameters_status', 'validate_motor_state', 'parameters_fresh'):
            self.assertIs(getattr(motor, name), getattr(protocol, name))

    def test_all_import_orders_and_actual_app_single_user_contract_without_io(self):
        probe = Path(__file__).with_name('fixtures') / 'hc16_import_probe.py'
        result = subprocess.run([sys.executable, '-B', str(probe)], capture_output=True,
                                text=True, timeout=30, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['import_orders'], 120)
        self.assertEqual(value['rejected_origins'], 28)
        self.assertFalse(value['external_work'])
        for name in ('single_superuser', 'obsolete_settings_absent', 'native_token_private'):
            self.assertTrue(value[name])


if __name__ == '__main__':
    unittest.main()
