import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('r22_start_tested', Path(__file__).with_name('start_r22.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
spec = importlib.util.spec_from_file_location('r22_diagnostic_tested', Path(__file__).with_name('summarize_r21_baseline_failure.py'))
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class StartR22Tests(unittest.TestCase):
    def fixture(self, directory):
        base = Path(directory); prior = base / 'prior'; kit = base / 'kit'
        core = SimpleNamespace(STATE=kit / 'private/transition', RUNTIME=base / 'runtime', PRIVATE=base / 'private-runtime',
                               guard_runtime=Mock(), active=Mock(return_value=False))
        old = {'source_sha256': {'file' + str(i): 'source' for i in range(799)}}
        write(prior / 'release.json', old)
        write(prior / 'deployment-status.json', {'phase': 'baseline_full_backup'})
        job = {'run_id': r.RUN, 'state': 'failed', 'mode': 'weekly', 'scope': 'router', 'pid': 1234567,
               'targets': {name: {'state': 'succeeded'} for name in ('local_archive', 'secrets_bundle', 'git_offsite')},
               'archive': {'completed': True, 'sha256': r.ARCHIVE_SHA}}
        job['targets']['restic'] = {'state': 'failed', 'detail': 'Router snapshot failed; local archive retained; restic backup exit 1'}
        write(base / 'backups/backup-state.json', job); write(base / 'backups/runs' / (r.RUN + '.json'), job)
        return base, prior, kit, core, job

    def guard(self, base, prior, core):
        with patch.object(r, 'BASE', base), patch.object(r, 'PRIOR', prior), \
             patch.object(r, 'digest', side_effect=lambda p: r.PRIOR_MANIFEST if p == prior / 'release.json' else 'source'), \
             patch.object(r.os, 'kill', side_effect=ProcessLookupError):
            return r.guard_state(core, {})

    def test_exact_failed_run_and_unchanged_runtime_allow_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            base, prior, kit, core, job = self.fixture(directory)
            self.assertEqual(self.guard(base, prior, core), job)
            core.guard_runtime.assert_called_once_with({})

    def test_new_transition_or_runtime_blocks_before_runtime_probe(self):
        for name in ('STATE', 'RUNTIME', 'PRIVATE'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                base, prior, kit, core, job = self.fixture(directory)
                getattr(core, name).mkdir(parents=True)
                with self.assertRaisesRegex(r.StartError, 'CUTOVER_OR_HANDOVER'):
                    self.guard(base, prior, core)
                core.guard_runtime.assert_not_called()

    def test_newer_backup_is_not_overwritten_or_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            base, prior, kit, core, job = self.fixture(directory)
            write(base / 'backups/backup-state.json', {**job, 'run_id': 'new'})
            with self.assertRaisesRegex(r.StartError, 'FAILED_RUN_CHANGED'): self.guard(base, prior, core)

    def test_missing_successful_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, prior, kit, core, job = self.fixture(directory)
            job['targets']['git_offsite']['state'] = 'failed'
            write(base / 'backups/backup-state.json', job); write(base / 'backups/runs' / (r.RUN + '.json'), job)
            with self.assertRaisesRegex(r.StartError, 'FAILED_RUN_SCOPE_CHANGED'): self.guard(base, prior, core)

    def test_changed_prior_phase_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base, prior, kit, core, job = self.fixture(directory)
            write(prior / 'deployment-status.json', {'phase': 'cutover'})
            with self.assertRaisesRegex(r.StartError, 'PRIOR_PHASE_CHANGED'): self.guard(base, prior, core)

    def test_old_supervisor_must_be_inactive(self):
        with tempfile.TemporaryDirectory() as directory:
            base, prior, kit, core, job = self.fixture(directory)
            core.active.return_value = True
            with self.assertRaisesRegex(r.StartError, 'SUPERVISOR_STILL_ACTIVE'): self.guard(base, prior, core)

    def test_live_failed_runner_pid_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            base, prior, kit, core, job = self.fixture(directory)
            with patch.object(r, 'BASE', base), patch.object(r, 'PRIOR', prior), \
                 patch.object(r, 'digest', side_effect=lambda p: r.PRIOR_MANIFEST if p == prior / 'release.json' else 'source'), \
                 patch.object(r.os, 'kill'):
                with self.assertRaisesRegex(r.StartError, 'PID_STILL_EXISTS'): r.guard_state(core, {})

    def diagnostic_fixture(self, directory):
        base = Path(directory)
        log = base / 'backups/router-diagnostics' / (r.RUN + '-' + 'a' * 32 + '.json')
        log.parent.mkdir(parents=True); log.write_text('private diagnostic placeholder')
        stderr = ('rclone: data/aa/' + 'a' * 64 + ': Put mkParentDir failed: write tcp 192.0.2.2:1234->192.0.2.1:21: i/o timeout\n'
                  'rclone: locks/' + 'b' * 64 + ': Delete request remove error: write tcp 192.0.2.2:1234->192.0.2.1:21: i/o timeout\n'
                  'Failed to save pack: 500 Internal Server Error')
        payload = {'run_id': r.RUN, 'tool': 'restic', 'operation': 'backup', 'exit_code': 1,
                   'stderr': stderr, 'stderr_truncated': False, 'stdout_truncated': True}
        error = {'error_type': 'RuntimeError', 'detail': 'Release operation failed: systemd-run'}
        diag = SimpleNamespace(read_private=lambda path: payload if path == log else error, summary=d.summary)
        return base, payload, error, diag

    def test_private_error_must_prove_control_write_and_lock_cleanup_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            base, payload, error, diag = self.diagnostic_fixture(directory)
            with patch.object(r, 'BASE', base): result = r.guard_failure(diag)
            self.assertTrue(result['ok']); self.assertTrue(result['original_failed_backup_not_adopted'])
            self.assertNotIn('192.0.2', json.dumps(result))

    def test_truncated_stderr_prevents_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            base, payload, error, diag = self.diagnostic_fixture(directory)
            payload['stderr_truncated'] = True
            with patch.object(r, 'BASE', base), self.assertRaisesRegex(r.StartError, 'DIAGNOSTIC_CHANGED'):
                r.guard_failure(diag)

    def test_corruption_or_disk_full_is_not_reclassified_as_idle_bug(self):
        for detail in ('ciphertext verification failed', 'no space left on device'):
            with self.subTest(detail=detail), tempfile.TemporaryDirectory() as directory:
                base, payload, error, diag = self.diagnostic_fixture(directory)
                payload['stderr'] += '\n' + detail
                with patch.object(r, 'BASE', base), self.assertRaisesRegex(r.StartError, 'UNEXPECTED_ERROR_CLASS'):
                    r.guard_failure(diag)

    def test_data_port_timeout_is_not_accepted_as_control_connection_bug(self):
        with tempfile.TemporaryDirectory() as directory:
            base, payload, error, diag = self.diagnostic_fixture(directory)
            payload['stderr'] = payload['stderr'].replace(':21:', ':54321:')
            with patch.object(r, 'BASE', base), self.assertRaisesRegex(r.StartError, 'CONTROL_WRITE_TIMEOUT_NOT_PROVEN'):
                r.guard_failure(diag)

    def test_unrelated_continuation_exception_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            base, payload, error, diag = self.diagnostic_fixture(directory)
            error['detail'] = 'different failure'
            with patch.object(r, 'BASE', base), self.assertRaisesRegex(r.StartError, 'UNEXPECTED_CONTINUATION_ERROR'):
                r.guard_failure(diag)

    def test_nonroot_cannot_load_or_start_any_release(self):
        with patch.object(r.os, 'geteuid', return_value=1000), patch.object(r, 'load') as load:
            with self.assertRaisesRegex(r.StartError, 'LOCAL_SUDO_REQUIRED'): r.main()
        load.assert_not_called()

    def test_tampered_lock_or_diagnostic_tool_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            kit = Path(directory); (kit / 'tools').mkdir()
            hashes = {}
            for name in ('resume_r21.py', 'summarize_r21_baseline_failure.py'):
                path = kit / 'tools' / name; path.write_text('original'); hashes[name] = r.digest(path)
            (kit / 'tools/resume_r21.py').write_text('changed')
            with patch.object(r, 'KIT', kit), self.assertRaisesRegex(r.StartError, 'ACTIVATION_TOOL_CHANGED'):
                r.verify_tools({'activation_tools_sha256': hashes})


if __name__ == '__main__': unittest.main(verbosity=2)
