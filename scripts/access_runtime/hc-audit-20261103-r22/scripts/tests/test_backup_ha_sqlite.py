import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]/'backup_ha_sqlite.py'
spec = importlib.util.spec_from_file_location('ha_sqlite_snapshot', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HomeAssistantSQLiteTest(unittest.TestCase):
    def test_committed_wal_is_included_without_uncommitted_transaction_or_stale_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'; source.mkdir()
            target = root/'target'; target.mkdir()
            live = sqlite3.connect(source/'home-assistant_v2.db')
            self.addCleanup(live.close)
            live.execute('pragma journal_mode=wal')
            live.execute('create table events(value text)'); live.commit()
            live.execute("insert into events values('committed')"); live.commit()
            live.execute("insert into events values('uncommitted')")
            # Use a separate read connection while the writer transaction is open.
            for suffix in ('-wal', '-shm'):
                (target/('home-assistant_v2.db'+suffix)).write_bytes(b'stale')
            result = module.snapshot(source, target)
            self.assertTrue(result['consistent_online_copy'])
            with sqlite3.connect(target/'home-assistant_v2.db') as copy:
                self.assertEqual(copy.execute('select value from events').fetchall(), [('committed',)])
            self.assertFalse((target/'home-assistant_v2.db-wal').exists())
            self.assertFalse((target/'home-assistant_v2.db-shm').exists())
            live.rollback()

    def test_symlink_sidecar_is_rejected_before_replacing_previous_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'; source.mkdir()
            target = root/'target'; target.mkdir()
            with sqlite3.connect(source/'home-assistant_v2.db') as db:
                db.execute('create table events(value int)')
            old = target/'home-assistant_v2.db'; old.write_bytes(b'previous backup')
            outside = root/'outside'; outside.write_bytes(b'untouched')
            (target/'home-assistant_v2.db-wal').symlink_to(outside)
            with self.assertRaises(ValueError): module.snapshot(source, target)
            self.assertEqual(old.read_bytes(), b'previous backup')
            self.assertEqual(outside.read_bytes(), b'untouched')


if __name__ == '__main__':
    unittest.main()
