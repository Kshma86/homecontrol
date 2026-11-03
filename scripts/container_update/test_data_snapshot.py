import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

s=importlib.util.spec_from_file_location('data_snapshot',Path(__file__).with_name('data_snapshot.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class DataRollback(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.roots={n:self.base/n for n in ('mqtt','zigbee')}
        for p in self.roots.values():p.mkdir();(p/'state').write_text('old')
        self.patch=patch.object(m,'ROOTS',self.roots);self.patch.start();self.addCleanup(self.patch.stop)

    def test_restore_old_data_removes_new_entries_but_keeps_logs(self):
        z=self.roots['zigbee'];(z/'log').mkdir();(z/'log/live.log').write_text('before')
        target=self.base/'snapshot';m.capture(target)
        for p in self.roots.values():(p/'state').write_text('new');(p/'new-field').write_text('new')
        (z/'log/live.log').write_text('after')
        m.restore(target)
        for p in self.roots.values():
            self.assertEqual((p/'state').read_text(),'old');self.assertFalse((p/'new-field').exists())
        self.assertEqual((z/'log/live.log').read_text(),'after')

    def test_symlink_is_rejected_before_capture(self):
        (self.roots['mqtt']/'link').symlink_to('/etc/hostname')
        with self.assertRaises(ValueError):m.capture(self.base/'snapshot')

    def test_invalid_saved_path_is_rejected_before_deleting_live_data(self):
        target=self.base/'snapshot';m.capture(target)
        p=target/'metadata.json';data=json.loads(p.read_text());data['mqtt'][0]['path']='../outside';p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):m.restore(target)
        self.assertEqual((self.roots['mqtt']/'state').read_text(),'old')

    def test_missing_snapshot_file_does_not_delete_current_data(self):
        target=self.base/'snapshot';m.capture(target);(target/'mqtt/state').unlink()
        with self.assertRaises(ValueError):m.restore(target)
        self.assertTrue((self.roots['mqtt']/'state').exists())


if __name__=='__main__':unittest.main()
