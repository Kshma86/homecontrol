import importlib.util
from contextlib import redirect_stderr
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('r22_idle_operator_tested', Path(__file__).with_name('run_r22_when_idle.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


class IdleTests(unittest.TestCase):
    def exercise_main(self, root, ready):
        entry = root / 'entry.py'; entry.write_text('synthetic verified entry')
        core = SimpleNamespace(verify=Mock(return_value={'sealed': True}))
        resume = SimpleNamespace(verify_sidecar=Mock(), load=Mock(return_value=SimpleNamespace(router=SimpleNamespace(core=core))),
                                 KIT=root, rebase_manifest=ready, main=Mock(), ResumeError=type('ResumeError', (ValueError,), {}))
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=Mock()))
        def make_private(path): path.mkdir(mode=0o700, exist_ok=True)
        with patch.object(r, 'SIDECAR', root), patch.object(r, 'ENTRY', entry), \
             patch.object(r, 'ENTRY_SHA256', hashlib.sha256(entry.read_bytes()).hexdigest()), \
             patch.object(r.os, 'geteuid', return_value=0), patch.object(r.os, 'umask'), \
             patch.object(r, 'protected_directory', side_effect=make_private), \
             patch.object(r.importlib.util, 'spec_from_file_location', return_value=spec), \
             patch.object(r.importlib.util, 'module_from_spec', return_value=resume), \
             patch.dict(r.os.environ), redirect_stderr(io.StringIO()):
            try: r.main()
            except ValueError: pass
        return resume

    def test_non_robot_guard_blocks_activation_and_creates_early_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resume = self.exercise_main(root, Mock(side_effect=ValueError('Active irrigation session')))
            resume.main.assert_not_called()
            logs = list((root / 'private').glob('early-error-*.json')); self.assertEqual(len(logs), 1)
            self.assertEqual(json.loads(logs[0].read_text())['phase'], 'wait_robot_idle')
            self.assertFalse((root / 'private/started.json').exists())

    def test_successful_preflight_calls_the_original_entry_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); resume = self.exercise_main(root, Mock(return_value={'ready': True}))
            resume.verify_sidecar.assert_called_once()
            resume.main.assert_called_once_with()
            self.assertFalse(list((root / 'private').glob('early-error-*.json')))

    def test_waits_only_for_robot_then_returns_successful_guard(self):
        ready = Mock(side_effect=[ValueError(r.ROBOT_GATE), ValueError(r.ROBOT_GATE), {'ok': True}])
        now = [0]
        def sleep(seconds): now[0] += seconds
        result = r.wait_for_robot(ready, clock=lambda: now[0], sleep=sleep, report=Mock())
        self.assertEqual(result, {'ok': True}); self.assertEqual(now[0], 60)

    def test_idle_robot_does_not_wait(self):
        sleep = Mock(); r.wait_for_robot(lambda: True, sleep=sleep); sleep.assert_not_called()

    def test_other_guard_error_is_not_retried(self):
        for error in (ValueError('Active irrigation session'), PermissionError('Private input')):
            with self.subTest(error=error):
                sleep = Mock()
                with self.assertRaises(type(error)): r.wait_for_robot(Mock(side_effect=error), sleep=sleep)
                sleep.assert_not_called()

    def test_robot_wait_is_bounded(self):
        now = [0]
        def sleep(seconds): now[0] += seconds
        with self.assertRaisesRegex(ValueError, 'timed out'):
            r.wait_for_robot(Mock(side_effect=ValueError(r.ROBOT_GATE)), timeout=31,
                             clock=lambda: now[0], sleep=sleep, report=Mock())
        self.assertEqual(now[0], 31)

    def test_started_entry_is_never_repeated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); r.require_unstarted(root); (root / 'started.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'already started'): r.require_unstarted(root)

    def test_early_error_is_saved_privately_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'error.json'
            try: raise ValueError('Synthetic private details')
            except ValueError as error: r.save_error(path, 'verify_release', error)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            value = json.loads(path.read_text()); self.assertEqual(value['phase'], 'verify_release')
            self.assertTrue(value['frames'])
            with self.assertRaises(FileExistsError): r.save_error(path, 'again', ValueError('new'))

    def test_error_log_symlink_is_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'target'; target.write_text('keep'); link = root / 'link'; link.symlink_to(target)
            with self.assertRaises(FileExistsError): r.save_error(link, 'verify_release', ValueError('error'))
            self.assertEqual(target.read_text(), 'keep')

    def test_nonroot_does_not_load_entry_or_create_diagnostics(self):
        with patch.object(r.os, 'geteuid', return_value=1000), patch.object(r, 'protected_directory') as create:
            with self.assertRaises(PermissionError): r.main()
        create.assert_not_called()


if __name__ == '__main__': unittest.main()
