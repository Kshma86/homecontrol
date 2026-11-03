"""Safety and failure-boundary tests; no host mutation or Docker execution."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('host_execute', Path(__file__).with_name('execute.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def good_backup():
    state = {'run_id': 'new', 'mode': 'weekly', 'state': 'completed', 'returncode': 0, 'scope': 'router',
             'targets': {n: {'state': 'succeeded'} for n in
                         ('local_archive', 'restic', 'git_offsite', 'secrets_bundle', 'restic_retention')},
             'archive': {'completed': True, 'run_id': 'new', 'mode': 'weekly',
                         'coverage': {n: True for n in m.COVERAGE}, 'sha256': 'abc'}}
    smoke = {'ok': True, 'snapshot_id': 'snapshot', 'filesystem': 'sha256_verified',
             'restic': 'sha256_verified', 'database': 'restore_verified_without_owner_acl',
             'restic_archive': {'sha256': 'abc'}, 'local_archive': {'sha256': 'abc'},
             'database_archive_sha256': 'abc'}
    return state, smoke


class BackupGates(unittest.TestCase):
    def test_fresh_complete_backup(self):
        self.assertEqual(m.validate_backup(*good_backup(), 'old')['run_id'], 'new')

    def test_old_run_rejected(self):
        with self.assertRaises(ValueError): m.validate_backup(*good_backup(), 'new')

    def test_incomplete_targets_rejected(self):
        for name in good_backup()[0]['targets']:
            state, smoke = good_backup(); state['targets'][name]['state'] = 'failed'
            with self.subTest(target=name), self.assertRaises(ValueError): m.validate_backup(state, smoke, 'old')

    def test_every_coverage_area_required(self):
        for name in m.COVERAGE:
            state, smoke = good_backup(); del state['archive']['coverage'][name]
            with self.subTest(area=name), self.assertRaises(ValueError): m.validate_backup(state, smoke, 'old')

    def test_restore_of_another_archive_rejected(self):
        for name in ('restic_archive', 'local_archive'):
            state, smoke = good_backup(); smoke[name]['sha256'] = 'wrong'
            with self.subTest(archive=name), self.assertRaises(ValueError): m.validate_backup(state, smoke, 'old')
        state, smoke = good_backup(); smoke['database_archive_sha256'] = 'wrong'
        with self.assertRaises(ValueError): m.validate_backup(state, smoke, 'old')

    def test_invalid_scope_or_exit_rejected(self):
        for field, value in [('scope', 'local_only'), ('returncode', 1), ('state', 'running'), ('mode', 'local')]:
            state, smoke = good_backup(); state[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): m.validate_backup(state, smoke, 'old')

    def test_incomplete_pg_restore_rejected(self):
        state, smoke = good_backup(); smoke['database'] = 'not_run'
        with self.assertRaises(ValueError): m.validate_backup(state, smoke, 'old')


class InventoryGates(unittest.TestCase):
    def setUp(self):
        self.before = {n: {'id': n + '-id', 'image': n + '-image', 'running': True} for n in m.START}
        self.before['homecontrol-adminer'] = {'id': 'adminer-id', 'image': 'adminer-image', 'running': False}
        self.rows = [{'Name': '/' + n, 'Id': b['id'], 'Image': b['image'],
                      'State': {'Running': b['running']}, 'HostConfig': {'RestartPolicy': {'Name': 'unless-stopped'}}}
                     for n, b in self.before.items()]

    def test_accepted_inventory_includes_stopped_adminer(self):
        m.validate_inventory(self.rows, self.before)
        self.assertNotIn('homecontrol-adminer', m.START)

    def test_changed_image_identity_or_state_rejected(self):
        for key in ('Id', 'Image'):
            rows = copy.deepcopy(self.rows); rows[0][key] = 'changed'
            with self.subTest(field=key), self.assertRaises(ValueError): m.validate_inventory(rows, self.before)
        rows = copy.deepcopy(self.rows); rows[0]['State']['Running'] = False
        with self.assertRaises(ValueError): m.validate_inventory(rows, self.before)

    def test_restart_always_is_not_safe_for_ordered_upgrade(self):
        self.rows[0]['HostConfig']['RestartPolicy']['Name'] = 'always'
        with self.assertRaises(ValueError): m.validate_inventory(self.rows, self.before)

    def test_unlisted_container_rejected(self):
        with self.assertRaises(ValueError): m.validate_inventory(self.rows[:-1], self.before)


class FirewallGates(unittest.TestCase):
    def test_live_counters_and_handles_are_ignored(self):
        a = {'rule': {'handle': 4, 'expr': [{'counter': {'packets': 1, 'bytes': 50}}, {'drop': None}]}}
        b = {'rule': {'handle': 9, 'expr': [{'counter': {'packets': 8, 'bytes': 900}}, {'drop': None}]}}
        self.assertEqual(m.normalize_nft(a), m.normalize_nft(b))

    def test_firewall_action_change_is_detected(self):
        self.assertNotEqual(m.normalize_nft({'rule': {'expr': [{'drop': None}]}}),
                            m.normalize_nft({'rule': {'expr': [{'accept': None}]}}))

    def test_device_probe_requires_an_explicit_online_state(self):
        for payload in ('offline', '{"state":"offline"}', '{"state":"not_online"}', 'online later'):
            with self.subTest(payload=payload), patch.object(m, 'call', return_value=payload):
                with self.assertRaises(ValueError): m.device_connections()
        with patch.object(m, 'call', side_effect=['{"state":"online"}', '']) as call:
            self.assertEqual(m.device_connections()['actuation_commands'], 0)
            self.assertEqual(call.call_count, 2)


class FailureBoundaries(unittest.TestCase):
    def test_partial_pause_restores_original_active_units(self):
        calls = []
        def fake(args, **kwargs):
            calls.append(args)
            if args == ['systemctl', 'stop', m.QUIESCE[1]]: raise RuntimeError('test failure')
            return ''
        with patch.object(m, 'active', return_value=True), patch.object(m, 'write'), patch.object(m, 'call', side_effect=fake):
            with self.assertRaises(RuntimeError): m.pause()
        self.assertEqual([a[2] for a in calls if a[1] == 'start'], list(m.QUIESCE))

    def test_backup_failure_cannot_reach_apt_or_container_stop(self):
        check = Mock(); baseline = {'boot_id': 'boot', 'dpkg_audit': '', 'holds': [],
                                    'containers': {n: {'id': n, 'image': n, 'running': True} for n in m.START}}
        check.snapshot.return_value = baseline
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            def fake(args, **kwargs):
                calls.append(list(map(str, args)))
                if args[:2] == ['docker', 'inspect']: return '[]'
                if args[0] == 'tar': Path(args[5]).write_text('private snapshot')
                return ''
            with patch.object(m, 'STATE', Path(tmp)), patch.object(m, 'checks', return_value=check), \
                 patch.object(m, 'read', return_value={'boot_id': 'boot'}), patch.object(m, 'call', side_effect=fake), \
                 patch.object(m, 'validate_inventory'), patch.object(m, 'physical_guard'), patch.object(m, 'idle'), \
                 patch.object(m, 'space_guard'), patch.object(m, 'firewall', return_value={}), \
                 patch.object(m, 'common_locks'), patch.object(m, 'pause', return_value={'x.timer': True}), \
                 patch.object(m, 'resume') as resumed, \
                 patch.object(m, 'backup_restore', side_effect=ValueError('backup failure')):
                with self.assertRaises(ValueError): m.upgrade()
                resumed.assert_called_once_with({'x.timer': True})
        self.assertFalse(any(a[0] == 'apt-get' or a[:2] == ['docker', 'stop'] for a in calls))


if __name__ == '__main__': unittest.main()
