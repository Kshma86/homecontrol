"""Fault injection for the r21 stale-lock recovery and guarded continuation."""
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('resume_r21_tested', Path(__file__).with_name('resume_r21.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def metadata(pid=99999999, host='fixture-host'):
    return {'hostname': host, 'pid': pid, 'time': datetime.now(timezone.utc).isoformat(), 'exclusive': True}


class LockRecoveryTest(unittest.TestCase):
    def test_dead_local_owner_is_required(self):
        with patch.object(r.socket, 'gethostname', return_value='fixture-host'), patch.object(r.os, 'kill', side_effect=ProcessLookupError):
            proof = r.validate_lock(metadata())
        self.assertTrue(proof['same_host']); self.assertFalse(proof['process_exists'])

    def test_live_process_is_never_unlocked(self):
        with patch.object(r.socket, 'gethostname', return_value='fixture-host'), patch.object(r.os, 'kill'):
            with self.assertRaisesRegex(r.ResumeError, 'PROCESS_STILL_EXISTS'): r.validate_lock(metadata())

    def test_foreign_host_is_never_unlocked_even_if_pid_is_absent(self):
        with patch.object(r.socket, 'gethostname', return_value='different-host'), patch.object(r.os, 'kill') as kill:
            with self.assertRaisesRegex(r.ResumeError, 'OTHER_HOST'): r.validate_lock(metadata())
        kill.assert_not_called()

    def test_permission_failure_is_not_proof_of_dead_owner(self):
        with patch.object(r.socket, 'gethostname', return_value='fixture-host'), patch.object(r.os, 'kill', side_effect=PermissionError):
            with self.assertRaisesRegex(r.ResumeError, 'NOT_PROVEN_DEAD'): r.validate_lock(metadata())

    def test_missing_boolean_or_system_pid_is_rejected(self):
        for pid in (None, True, 0, 1, '9999'):
            with self.subTest(pid=pid), patch.object(r.socket, 'gethostname', return_value='fixture-host'), patch.object(r.os, 'kill') as kill:
                with self.assertRaisesRegex(r.ResumeError, 'INVALID_LOCK_PID'): r.validate_lock(metadata(pid))
                kill.assert_not_called()

    def test_future_or_naive_timestamp_is_rejected(self):
        for stamp in ('2999-01-01T00:00:00+00:00', '2026-01-01T00:00:00'):
            with self.subTest(stamp=stamp), patch.object(r.socket, 'gethostname', return_value='fixture-host'), patch.object(r.os, 'kill') as kill:
                with self.assertRaisesRegex(r.ResumeError, 'INVALID_LOCK_TIME'): r.validate_lock({**metadata(), 'time': stamp})
                kill.assert_not_called()

    def test_go_variable_fractional_precision_is_supported_on_python310(self):
        for stamp in ('2026-01-01T00:00:00.024623931Z', '2026-01-01T00:00:00.1+01:00', '2026-01-01T00:00:00Z'):
            with self.subTest(stamp=stamp), patch.object(r.socket, 'gethostname', return_value='fixture-host'), patch.object(r.os, 'kill', side_effect=ProcessLookupError):
                self.assertFalse(r.validate_lock({**metadata(), 'time': stamp})['process_exists'])

    def repo(self, locks=('a' * 64,)):
        ids = '\n'.join(locks)
        return SimpleNamespace(call=Mock(side_effect=[ids, *[json.dumps(metadata()) for _ in locks], ids, '', '']))

    def test_native_unlock_has_no_force_and_after_list_must_be_empty(self):
        repo = self.repo(); save = Mock()
        with patch.object(r, 'validate_lock', return_value={'process_exists': False}), patch('builtins.print'):
            proof = r.remove_stale(repo, save)
        self.assertTrue(proof['ok']); self.assertFalse(proof['force_used'])
        calls = [call.args[0] for call in repo.call.call_args_list]
        self.assertIn(['unlock'], calls)
        self.assertEqual(calls[-1], ['--no-lock', 'list', 'locks'])
        self.assertFalse(any('--remove-all' in args or 'forget' in args or 'prune' in args for args in calls))
        save.assert_called_once()

    def test_all_lock_owners_are_checked_before_any_unlock(self):
        repo = self.repo(('a' * 64, 'b' * 64))
        with patch.object(r, 'validate_lock', side_effect=[{}, r.ResumeError('LOCK_PROCESS_STILL_EXISTS')]):
            with self.assertRaisesRegex(r.ResumeError, 'PROCESS_STILL_EXISTS'): r.remove_stale(repo, Mock())
        self.assertFalse(any(call.args[0] == ['unlock'] for call in repo.call.call_args_list))

    def test_inventory_change_prevents_unlock(self):
        repo = self.repo(); repo.call.side_effect = ['a' * 64, json.dumps(metadata()), 'b' * 64]
        with patch.object(r, 'validate_lock', return_value={}):
            with self.assertRaisesRegex(r.ResumeError, 'INVENTORY_CHANGED'): r.remove_stale(repo, Mock())
        self.assertFalse(any(call.args[0] == ['unlock'] for call in repo.call.call_args_list))

    def test_native_unlock_failure_is_not_suppressed(self):
        repo = self.repo(); repo.call.side_effect = ['a' * 64, json.dumps(metadata()), 'a' * 64, RuntimeError('transport failure')]
        with patch.object(r, 'validate_lock', return_value={}), patch('builtins.print'):
            with self.assertRaisesRegex(RuntimeError, 'transport failure'): r.remove_stale(repo, Mock())

    def test_a_remaining_lock_blocks_activation(self):
        repo = self.repo(); repo.call.side_effect = ['a' * 64, json.dumps(metadata()), 'a' * 64, '', 'a' * 64]
        with patch.object(r, 'validate_lock', return_value={}), patch('builtins.print'):
            with self.assertRaisesRegex(r.ResumeError, 'STILL_LOCKED'): r.remove_stale(repo, Mock())

    def test_empty_inventory_never_writes_repository(self):
        repo = SimpleNamespace(call=Mock(side_effect=['', '', '']))
        proof = r.remove_stale(repo, Mock())
        self.assertTrue(proof['ok']); self.assertFalse(proof['native_unlock_attempted'])
        self.assertTrue(all(call.args[0] == ['--no-lock', 'list', 'locks'] for call in repo.call.call_args_list))

    def test_malformed_or_duplicate_lock_inventory_is_rejected(self):
        for output in ('not-an-id', 'a' * 64 + '\n' + 'a' * 64):
            with self.subTest(output=output), self.assertRaises(r.ResumeError):
                r.lock_ids(SimpleNamespace(call=Mock(return_value=output)))


class ContinuationGuardTest(unittest.TestCase):
    def fixture(self, directory):
        base = Path(directory); kit = base / 'kit'; (kit / 'private').mkdir(parents=True)
        (kit / 'private/audit-error.json').write_text(json.dumps({'error_type': 'RuntimeError', 'detail': 'Restic operation failed (exit 1); repository was not reinitialized'}))
        core = SimpleNamespace(STATE=kit / 'private/transition', RUNTIME=base / 'runtime', PRIVATE=base / 'installed-private', guard_runtime=Mock())
        return base, kit, core

    def test_only_known_precheck_error_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core = self.fixture(directory)
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit): r.guard(core, {})
            core.guard_runtime.assert_called_once()

    def test_another_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, core = self.fixture(directory)
            (kit / 'private/audit-error.json').write_text(json.dumps({'error_type': 'ValueError', 'detail': 'other'}))
            with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.ResumeError, 'UNEXPECTED_ORIGINAL'): r.guard(core, {})
            core.guard_runtime.assert_not_called()

    def test_any_started_cutover_or_backup_staging_blocks_continuation(self):
        for state in ('transition', 'runtime', 'baseline-runner', 'progress.json'):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                base, kit, core = self.fixture(directory); (kit / 'private' / state).mkdir()
                with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaises(r.ResumeError): r.guard(core, {})
                core.guard_runtime.assert_not_called()

    def test_existing_deployment_status_or_handover_blocks_continuation(self):
        for name in ('kit/deployment-status.json', 'docs/audit-final-20261102.md', 'runtime', 'installed-private'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                base, kit, core = self.fixture(directory); path = base / name; path.parent.mkdir(parents=True, exist_ok=True); path.touch()
                with patch.object(r, 'BASE', base), patch.object(r, 'KIT', kit), self.assertRaises(r.ResumeError): r.guard(core, {})

    def test_nonroot_never_loads_release_or_changes_locks(self):
        with patch.object(r.os, 'geteuid', return_value=1000), patch.object(r, 'verify_sidecar') as verify:
            with self.assertRaisesRegex(r.ResumeError, 'LOCAL_SUDO'): r.main()
        verify.assert_not_called()

    def test_changed_continuation_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'file').write_text('old')
            (root / 'acceptance.json').write_text(json.dumps({'ok': True, 'sha256': {'file': r.digest(root / 'file')}}))
            (root / 'file').write_text('changed')
            with patch.object(r, 'SIDECAR', root), self.assertRaisesRegex(r.ResumeError, 'CONTINUATION_CHANGED'): r.verify_sidecar()


class PrecheckLockingTest(unittest.TestCase):
    def fixture(self, root):
        events = []
        class Repository:
            def __init__(self, settings, **kwargs): self.settings = settings
            def check(self): events.append('check')
        @contextmanager
        def locked():
            events.append('lock')
            try: yield
            finally: events.append('release')
        core = SimpleNamespace(STATE=root / 'transition', locked=lambda stack: stack.enter_context(locked()), idle=lambda: events.append('idle'))
        module = SimpleNamespace(router=SimpleNamespace(RouterRepository=Repository, core=core))
        logger = SimpleNamespace(OPERATIONS=set(), OperationLog=lambda root, run_id, run: run)
        with patch.object(r, 'load', return_value=logger): r.install_diagnostics(module, root)
        return module, events

    def test_production_precheck_uses_both_common_lock_adapter_and_idle_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            module, events = self.fixture(Path(directory))
            module.router.RouterRepository({'router_repository_path': '/G/hc-backup/restic/homecontrol'}).check()
        self.assertEqual(events, ['lock', 'idle', 'check', 'release'])

    def test_probe_check_does_not_acquire_production_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            module, events = self.fixture(Path(directory))
            module.router.RouterRepository({'router_repository_path': '/G/hc-backup/probes/router-r21'}).check()
        self.assertEqual(events, ['check'])

    def test_transaction_check_does_not_recursively_acquire_same_flock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); module, events = self.fixture(root); (root / 'transition').mkdir()
            module.router.RouterRepository({'router_repository_path': '/G/hc-backup/restic/homecontrol'}).check()
        self.assertEqual(events, ['check'])


class RealResticLockLab(unittest.TestCase):
    def test_real_lock_owner_validation_native_unlock_and_normal_full_check(self):
        with tempfile.TemporaryDirectory(prefix='hc-r21-native-lock-test-') as directory:
            root = Path(directory); password = root / 'password'
            password.write_text('disposable-local-test-fixture'); password.chmod(0o600)
            env = {k: v for k, v in os.environ.items() if not k.startswith(('RESTIC_', 'RCLONE_'))}
            env.update(RESTIC_REPOSITORY=str(root / 'repo'), RESTIC_PASSWORD_FILE=str(password), RESTIC_CACHE_DIR=str(root / 'cache'))
            def run(args): return subprocess.run(['restic', *args], env=env, capture_output=True, text=True, timeout=45)
            self.assertEqual(run(['init']).returncode, 0)
            child = subprocess.Popen(['restic', 'backup', '--stdin', '--stdin-filename', 'fixture'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            try:
                deadline = time.monotonic() + 15
                while not list((root / 'repo/locks').iterdir()):
                    self.assertIsNone(child.poll()); self.assertLess(time.monotonic(), deadline); time.sleep(.05)
                inventory = run(['--no-lock', 'list', 'locks']); self.assertEqual(inventory.returncode, 0)
                ids = inventory.stdout.splitlines(); self.assertEqual(len(ids), 1)
                details = run(['--no-lock', 'cat', 'lock', ids[0]]); self.assertEqual(details.returncode, 0)
                lock = json.loads(details.stdout)
                self.assertEqual(lock['pid'], child.pid)
                with self.assertRaisesRegex(r.ResumeError, 'PROCESS_STILL_EXISTS'): r.validate_lock(lock)
                self.assertEqual(run(['unlock']).returncode, 0)
                self.assertEqual(len(list((root / 'repo/locks').iterdir())), 1)
                self.assertEqual(run(['check', '--read-data']).returncode, 1)
                self.assertEqual(run(['--no-lock', 'check', '--read-data']).returncode, 0)
                child.kill(); child.wait(timeout=10); child.stdin.close()
                self.assertFalse(r.validate_lock(lock)['process_exists'])
                self.assertEqual(run(['unlock']).returncode, 0)
                self.assertEqual(list((root / 'repo/locks').iterdir()), [])
                self.assertEqual(run(['check', '--read-data']).returncode, 0)
            finally:
                if child.poll() is None: child.kill(); child.wait(timeout=10)
                if child.stdin is not None: child.stdin.close()


if __name__ == '__main__': unittest.main(verbosity=2)
