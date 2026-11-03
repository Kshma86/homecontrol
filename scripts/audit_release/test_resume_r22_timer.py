import copy
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('resume_r22_timer_tested', Path(__file__).with_name('resume_r22_timer.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))


class ResumeTimerTests(unittest.TestCase):
    def fixture(self, directory):
        base = Path(directory); kit = base / 'kit'; previous = base / 'previous'
        core = SimpleNamespace(OLD='r18', OLD_RUNTIME=base / 'r18-runtime', UNIT_ROOT=base / 'units',
            RUNTIME=base / 'runtime', PRIVATE=base / 'private-runtime', STATE=kit / 'private/transition',
            active=Mock(return_value=False), guard_runtime=Mock(),
            container=lambda n: 'homecontrol-' + n.removeprefix('homecontrol-'),
            platform=lambda: SimpleNamespace(no_symlinks=lambda p: None))
        for path in (core.RUNTIME, core.PRIVATE, kit / 'private/baseline-runner'): path.mkdir(parents=True)
        (core.RUNTIME / 'sealed.py').write_text('sealed source')
        manifest = {'source_sha256': {'sealed.py': r.digest(core.RUNTIME / 'sealed.py')},
                    'changed_services': ['backend', 'mdns', 'homecontrol-ha-growatt-poller'],
                    'baseline': {n: {'id': str(i) * 64, 'image': 'sha256:old-' + n} for i, n in enumerate(
                        ('homecontrol-backend', 'homecontrol-mdns', 'homecontrol-ha-growatt-poller', 'homecontrol-postgres'), 1)}}
        rows = {n: {'Id': ('a' * 64 if n != 'homecontrol-postgres' else before['id']), 'Image': before['image'],
                    'State': {'Running': True, 'Health': {'Status': 'healthy'}}} for n, before in manifest['baseline'].items()}
        core.call = Mock(side_effect=lambda args, **kwargs: SimpleNamespace(stdout=json.dumps([rows[args[2]]]).encode()))
        for root in (kit / 'private/runtime', core.PRIVATE):
            (root / 'images').mkdir(parents=True)
            (root / 'images/access-images.tar.gz').write_bytes(b'synthetic verified cache')
            (root / 'config').write_text('synthetic private bytes')
        write(core.PRIVATE / 'installed.json', {'release': r.NAME, 'state': 'running_requires_supervised_acceptance', 'transition': str(core.STATE)})
        write(core.STATE / 'result.json', {'state': 'rolled_back', 'success': True})
        write(core.STATE / 'transition.json', {'release': r.NAME})
        write(kit / 'deployment-status.json', {'phase': 'previous_release_restored'})
        error = {'error_type': 'ValueError', 'detail': 'Scheduled timer has no next trigger: homecontrol-post-boot-health.timer'}
        write(previous / 'private/continuation-error.json', error)
        proof = {'ok': True, 'release': r.NAME, 'run_id': r.RUN,
                 'snapshot_id': 'e13b233aefaeb74e4be4878acb576765d1cec77a1dbac7d6f67a6ab2239fa00b',
                 'restore': 'verified', 'database': 'verified', 'git': 'pushed', 'ai_enabled': False}
        write(kit / 'evidence/router-live-acceptance.json', proof)
        job = {'run_id': r.RUN, 'state': 'completed', 'returncode': 0, 'archive': {'sha256': r.ARCHIVE_SHA256},
               'targets': {n: {'state': 'succeeded'} for n in ('local_archive', 'restic', 'git_offsite', 'secrets_bundle', 'restic_retention')}}
        write(base / 'backups/backup-state.json', job); write(base / 'backups/runs' / (r.RUN + '.json'), job)
        return base, kit, previous, core, manifest, rows

    def guarded(self, fixture):
        base, kit, previous, core, manifest, rows = fixture
        with ExitStack() as stack:
            for key, value in (('BASE', base), ('KIT', kit), ('PREVIOUS', previous)):
                stack.enter_context(patch.object(r, key, value))
            old_units = stack.enter_context(patch.object(r, 'guard_old_units'))
            result = r.guard(core, manifest)
            old_units.assert_called_once_with(core)
            return result

    def test_recreated_three_r18_ids_are_adopted_without_mutating_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory); core, manifest = fixture[3:5]; original = copy.deepcopy(manifest)
            updated = r.rebase_manifest(core, manifest)
            self.assertEqual(manifest, original)
            self.assertEqual(updated['baseline']['homecontrol-postgres'], manifest['baseline']['homecontrol-postgres'])
            for name in ('homecontrol-backend', 'homecontrol-mdns', 'homecontrol-ha-growatt-poller'):
                self.assertEqual(updated['baseline'][name], {**manifest['baseline'][name], 'id': 'a' * 64})
            core.guard_runtime.assert_called_once_with(updated)

    def test_replaced_unchanged_container_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory); fixture[5]['homecontrol-postgres']['Id'] = 'b' * 64
            with self.assertRaisesRegex(r.ResumeError, 'UNCHANGED_R18'): r.rebase_manifest(fixture[3], fixture[4])

    def test_wrong_r18_image_is_rejected_even_for_changed_component(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory); fixture[5]['homecontrol-backend']['Image'] = 'sha256:r22'
            with self.assertRaisesRegex(r.ResumeError, 'R18_IMAGE_CHANGED'): r.rebase_manifest(fixture[3], fixture[4])

    def test_unhealthy_or_stopped_component_blocks_adoption(self):
        for state in ({'Running': False}, {'Running': True, 'Health': {'Status': 'unhealthy'}}):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(directory); fixture[5]['homecontrol-backend']['State'] = state
                with self.assertRaises(r.ResumeError): r.rebase_manifest(fixture[3], fixture[4])

    def test_exact_timer_failure_and_complete_install_after_rollback_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.guarded(self.fixture(directory))
            self.assertEqual(result['error_type'], 'ValueError')

    def test_other_timer_or_error_is_rejected(self):
        for error in ({'error_type': 'RuntimeError', 'detail': 'other'},
                      {'error_type': 'ValueError', 'detail': 'Scheduled timer has no next trigger: homecontrol-backup.timer'}):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(directory); write(fixture[2] / 'private/continuation-error.json', error)
                with self.assertRaisesRegex(r.ResumeError, 'UNEXPECTED_HANDOVER_ERROR'): self.guarded(fixture)

    def test_missing_or_failed_rollback_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory); write(fixture[3].STATE / 'result.json', {'state': 'failed'})
            with self.assertRaisesRegex(r.ResumeError, 'ROLLBACK_RESULT'): self.guarded(fixture)

    def test_final_handover_or_live_receipt_blocks_repeating(self):
        for name in ('docs/audit-final-20261102.md', 'kit/evidence/post-live-check.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(directory); write(fixture[0] / name, {})
                with self.assertRaisesRegex(r.ResumeError, 'HANDOVER_ALREADY_EXISTS'): self.guarded(fixture)

    def test_failed_restore_or_backup_target_is_rejected(self):
        for what in ('restore', 'target'):
            with self.subTest(what=what), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(directory)
                if what == 'restore':
                    p = fixture[1] / 'evidence/router-live-acceptance.json'; value = r.read(p); value['database'] = 'failed'
                else:
                    p = fixture[0] / 'backups/backup-state.json'; value = r.read(p); value['targets']['restic']['state'] = 'failed'
                write(p, value)
                with self.assertRaises(r.ResumeError): self.guarded(fixture)

    def test_newer_backup_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory); p = fixture[0] / 'backups/backup-state.json'; value = r.read(p); value['run_id'] = 'newer'; write(p, value)
            with self.assertRaisesRegex(r.ResumeError, 'COMPLETED_R22_RUN_CHANGED'): self.guarded(fixture)

    def test_private_or_runtime_drift_is_rejected_before_preserving(self):
        for what in ('runtime', 'private'):
            with self.subTest(what=what), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(directory); core = fixture[3]
                (core.RUNTIME / 'sealed.py' if what == 'runtime' else core.PRIVATE / 'config').write_text('changed')
                with self.assertRaises(r.ResumeError): self.guarded(fixture)

    def test_missing_image_cache_is_no_longer_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory); (fixture[3].PRIVATE / 'images/access-images.tar.gz').unlink()
            with self.assertRaisesRegex(r.ResumeError, 'FAILED_PRIVATE_TREE_CHANGED'): self.guarded(fixture)

    def test_busy_supervisor_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory); fixture[3].active.return_value = True
            with self.assertRaisesRegex(r.ResumeError, 'SUPERVISOR'): self.guarded(fixture)

    def test_previous_access_units_must_match_before_moving_r22_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, previous, core, manifest, rows = self.fixture(directory)
            core.OLD_RUNTIME.mkdir(); (core.OLD_RUNTIME / 'source.py').write_text('old sealed')
            write(base / 'backups/releases/r18/release.json', {'source_sha256': {'source.py': r.digest(core.OLD_RUNTIME / 'source.py')}})
            core.UNIT_ROOT.mkdir(); (core.UNIT_ROOT / 'docker.service.d').mkdir()
            (core.UNIT_ROOT / 'docker.service.d/hc-access.conf').write_text('still points at r22')
            common = SimpleNamespace(units=lambda *args, **kwargs: {'docker.service.d/hc-access.conf': 'r18 network guard'})
            with patch.object(r, 'BASE', base), patch.object(r, 'load', return_value=common), self.assertRaisesRegex(r.ResumeError, 'R18_ACCESS_UNIT_CHANGED'):
                r.guard_old_units(core)

    def test_nonroot_does_not_load_any_release(self):
        with patch.object(r.os, 'geteuid', return_value=1000), patch.object(r, 'verify_sidecar') as verify:
            with self.assertRaisesRegex(r.ResumeError, 'LOCAL_SUDO_REQUIRED'): r.main()
        verify.assert_not_called()

    def test_preservation_keeps_all_four_trees_and_refuses_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, previous, core, manifest, rows = self.fixture(directory)
            with patch.object(r, 'KIT', kit): moves = r.preserve_failed_install(core, 'test')
            self.assertEqual(len(moves), 4)
            for move in moves:
                self.assertFalse(Path(move['original']).exists())
                self.assertTrue(Path(move['preserved']).is_dir())
            self.assertEqual(Path(moves[0]['preserved'], 'sealed.py').read_text(), 'sealed source')
            source = base / 'source'; source.mkdir(); target = base / 'target'; target.mkdir()
            with self.assertRaises(FileExistsError): r.exclusive_rename(source, target)

    def test_partial_preservation_failure_restores_original_names(self):
        with tempfile.TemporaryDirectory() as directory:
            base, kit, previous, core, manifest, rows = self.fixture(directory)
            original = r.exclusive_rename; calls = 0
            def fail_second(source, target):
                nonlocal calls
                calls += 1
                if calls == 2: raise PermissionError('Synthetic rename failure')
                return original(source, target)
            with patch.object(r, 'KIT', kit), patch.object(r, 'exclusive_rename', side_effect=fail_second), self.assertRaises(PermissionError):
                r.preserve_failed_install(core, 'test')
            for path in (core.RUNTIME, core.PRIVATE, core.STATE, kit / 'private/baseline-runner'):
                self.assertTrue(path.is_dir())


if __name__ == '__main__': unittest.main()
