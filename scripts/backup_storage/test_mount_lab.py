"""Run only in an isolated user+mount namespace; no host systemd or Docker writes."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout
import migrate


class LabHost:
    def __init__(self, p, fail=None):
        self.p, self.fail = p, fail
        self.states = {name: True for name in (*migrate.WATCHERS, 'homecontrol-hostops.service')}
        self.running = True; self.restarts = 0; self.events = []
        self.mounts = {migrate.mount_name(p.source / name): (p.legacy / name if name else p.data, p.source / name)
                       for name in ('', *layout.PINNED)}

    def active(self, name): return self.states.get(name, False)
    def stop(self, name):
        self.events.append(('stop', name))
        if name in self.mounts:
            subprocess.run(['umount', str(self.mounts[name][1])], check=True)
        else: self.states[name] = False
    def start(self, name):
        self.events.append(('start', name))
        if name in self.mounts:
            if self.fail == name: self.fail = None; raise RuntimeError('injected mount failure')
            source, destination = self.mounts[name]
            subprocess.run(['mount', '--bind', str(source), str(destination)], check=True)
        else: self.states[name] = True
    def enable(self, name):
        if self.fail == 'enable': self.fail = None; raise RuntimeError('injected commit failure')
    def disable(self, name): pass
    def reload(self): pass
    def backend_stop(self):
        if self.fail == 'backend-stop': self.fail = None; raise RuntimeError('injected backend stop failure')
        self.running = False
    def backend_start(self): self.running = True; self.restarts += 1
    def guard(self, p, plan): pass
    def idle(self):
        if self.fail == 'busy': raise layout.StorageError('injected busy job')
    def daemon_mounts_ready(self, p): pass
    def healthy(self, p, plan):
        if self.fail == 'health': self.fail = None; raise RuntimeError('injected health failure')
        assert self.running
        assert (p.source / 'homecontrol_fixture.tar.gz').read_bytes() == b'archive-fixture'


class MountMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hc-storage-mount-lab-')
        root = Path(self.temp.name); var = root / 'var'; var.mkdir()
        subprocess.run(['mount', '-t', 'tmpfs', '-o', 'size=64m', 'tmpfs', str(var)], check=True)
        base = root / 'srv/homecontrol'; base.mkdir(parents=True)
        self.p = migrate.Paths(base=base, storage=var / 'storage', unit_root=root / 'units', helper=root / 'helper', var=var)
        self.p.unit_root.mkdir(); self.p.source.mkdir()
        (self.p.source / 'homecontrol_fixture.tar.gz').write_bytes(b'archive-fixture')
        (self.p.source / 'settings.json').write_text('{"fixture":true}')
        for name in layout.PINNED:
            path = self.p.source / name
            if name in ('releases', 'ai-control'):
                path.mkdir(); (path / 'fixture').write_bytes(b'pinned')
            else: path.touch(mode=0o660)
        self.original = {name: ((self.p.source / name).stat().st_dev, (self.p.source / name).stat().st_ino) for name in layout.PINNED}
        self.patch = patch.object(migrate.shutil, 'disk_usage', return_value=SimpleNamespace(free=200 * 1024 ** 3))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for name in reversed(['', *layout.PINNED]):
            path = self.p.source / name
            if migrate.is_mounted(path): subprocess.run(['umount', str(path)], check=True)
        subprocess.run(['umount', str(self.p.var)], check=True)
        self.temp.cleanup()

    def migration(self, fail=None):
        host = LabHost(self.p, fail)
        return migrate.Migration(self.p, host, {'active_release': 'fixture', 'containers': {}}), host

    def assert_original(self, host):
        self.assertFalse(self.p.source.is_mount()); self.assertFalse(self.p.legacy.exists())
        self.assertEqual((self.p.source / 'homecontrol_fixture.tar.gz').read_bytes(), b'archive-fixture')
        for name, expected in self.original.items():
            info = (self.p.source / name).stat(); self.assertEqual((info.st_dev, info.st_ino), expected)
        self.assertTrue(host.running); self.assertTrue(all(host.states[name] for name in migrate.WATCHERS))

    def test_real_cross_filesystem_mount_switch_cleanup_and_rollback(self):
        migration, host = self.migration(); migration.apply()
        self.assertTrue(migrate.check(self.p)['ok'])
        self.assertEqual(self.p.source.stat().st_dev, self.p.var.stat().st_dev)
        self.assertEqual(str((self.p.source / 'homecontrol_fixture.tar.gz').resolve()),
                         str(self.p.source / 'homecontrol_fixture.tar.gz'))
        for name, expected in self.original.items():
            info = (self.p.source / name).stat(); self.assertEqual((info.st_dev, info.st_ino), expected)
        self.assertFalse((self.p.legacy / 'homecontrol_fixture.tar.gz').exists())
        (self.p.source / 'new-backup.tar.gz').write_bytes(b'published-after-migration')
        migration.rollback(); self.assert_original(host)
        self.assertEqual((self.p.source / 'new-backup.tar.gz').read_bytes(), b'published-after-migration')

    def test_partial_mount_failure_restores_old_tree_and_lock_inodes(self):
        migration, host = self.migration(migrate.mount_name(self.p.source / 'ai-control'))
        with self.assertRaisesRegex(RuntimeError, 'mount failure'): migration.apply()
        self.assert_original(host)

    def test_health_failure_restores_original_without_losing_data(self):
        migration, host = self.migration('health')
        with self.assertRaisesRegex(RuntimeError, 'health failure'): migration.apply()
        self.assert_original(host)

    def test_failure_after_duplicate_cleanup_copies_data_back_before_unmount(self):
        migration, host = self.migration('enable')
        with self.assertRaisesRegex(RuntimeError, 'commit failure'): migration.apply()
        self.assert_original(host)

    def test_copy_corruption_never_switches_the_running_path(self):
        migration, host = self.migration()
        original = migrate.copy_tree
        def corrupt(source, destination):
            original(source, destination); (destination / 'homecontrol_fixture.tar.gz').write_bytes(b'corrupt')
        with patch.object(migrate, 'copy_tree', side_effect=corrupt), self.assertRaises(layout.StorageError): migration.apply()
        self.assert_original(host); self.assertEqual(host.restarts, 0)

    def test_saved_mount_units_can_reattach_all_pins_after_restart(self):
        migration, host = self.migration(); migration.apply()
        for name in reversed(['', *layout.PINNED]): host.stop(migrate.mount_name(self.p.source / name))
        with self.assertRaises(layout.StorageError): migrate.check(self.p)
        for name in ('', *layout.PINNED): host.start(migrate.mount_name(self.p.source / name))
        self.assertTrue(migrate.check(self.p)['ok'])
        for name, wanted in self.original.items():
            info = (self.p.source / name).stat(); self.assertEqual((info.st_dev, info.st_ino), wanted)

    def test_readonly_var_is_rejected_before_pausing_any_writer(self):
        migration, host = self.migration()
        subprocess.run(['mount', '-o', 'remount,bind,ro', str(self.p.var)], check=True)
        with self.assertRaisesRegex(layout.StorageError, 'read-only'): migration.apply()
        self.assertEqual(host.events, []); self.assert_original(host)

    def test_backend_stop_failure_preserves_original_tree(self):
        migration, host = self.migration('backend-stop')
        with self.assertRaisesRegex(RuntimeError, 'backend stop failure'): migration.apply()
        self.assert_original(host)

    def test_failure_between_source_rename_and_mountpoint_creation_is_reversible(self):
        migration, host = self.migration(); original = Path.mkdir; failed = False
        def mkdir(path, *args, **kwargs):
            nonlocal failed
            if path == self.p.source and self.p.legacy.exists() and not failed:
                failed = True; raise OSError('injected mountpoint creation failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'mkdir', mkdir), self.assertRaisesRegex(OSError, 'mountpoint creation failure'): migration.apply()
        self.assert_original(host)

    def test_rollback_space_failure_keeps_working_var_and_backend_running(self):
        migration, host = self.migration(); migration.apply(); restarts = host.restarts
        with patch.object(migrate.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(layout.StorageError, 'no longer fits'): migration.rollback()
        self.assertTrue(host.running); self.assertEqual(host.restarts, restarts)
        self.assertTrue(migrate.check(self.p, mounts_only=True)['ok'])
        self.assertTrue(all(host.states[name] for name in migrate.WATCHERS))

    def test_daemon_namespace_probe_uses_actual_nsenter_and_stat(self):
        migration, host = self.migration(); migration.apply()
        original = migrate.call
        def call(args, **kwargs):
            if args[:3] == ['systemctl', 'show', 'docker.service']:
                return SimpleNamespace(stdout=str(os.getpid()))
            return original(args, **kwargs)
        with patch.object(migrate, 'call', side_effect=call):
            migrate.Host().daemon_mounts_ready(self.p)

    def test_active_host_job_is_not_killed_or_paused(self):
        migration, host = self.migration('busy')
        with self.assertRaisesRegex(layout.StorageError, 'busy job'): migration.apply()
        self.assertEqual(host.events, []); self.assert_original(host)

    def test_existing_common_lock_is_not_interrupted_by_service_stop(self):
        migration, host = self.migration()
        with ExitStack() as stack:
            migrate.common_locks(self.p, stack)
            with self.assertRaises(BlockingIOError): migration.apply()
        self.assertEqual(host.events, []); self.assert_original(host)


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('Run with unshare --user --map-root-user --mount --fork; host root is not required')
    unittest.main(verbosity=2)
