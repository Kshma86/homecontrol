import importlib.util
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('container_update_probe',Path(__file__).with_name('probe.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Transactions(unittest.TestCase):
    def test_no_updates_is_an_explicit_empty_plan(self):
        self.assertEqual(m.parse_changes('debian','0 upgraded, 0 newly installed, 0 to remove.'),[])
        self.assertEqual(m.parse_changes('alpine','OK: 42 MiB in 21 packages'),[])

    def test_apt_upgrade_and_new_dependency(self):
        rows=m.parse_changes('debian','Inst openssl [3.0] (3.1 Debian:13/stable [amd64])\nInst libnew (1.0 Debian:13/stable [amd64])')
        self.assertEqual(rows,[{'package':'openssl','installed':'3.0','candidate':'3.1'}, {'package':'libnew','installed':None,'candidate':'1.0'}])

    def test_apk_upgrade_and_dependency(self):
        rows=m.parse_changes('alpine','(1/2) Upgrading busybox (1.0-r0 -> 1.0-r1)\n(2/2) Installing libnew (1.0-r0)')
        self.assertEqual(rows[0]['candidate'],'1.0-r1');self.assertIsNone(rows[1]['installed'])

    def test_unsafe_or_unparsed_changes_are_rejected(self):
        for family,text in [('debian','Remv curl [1.0]'),('debian','Inst ?broken'),
                            ('alpine','(1/1) Downgrading curl (2 -> 1)'),('alpine','Upgrading ?broken')]:
            with self.subTest(family=family,text=text),self.assertRaises(ValueError):m.parse_changes(family,text)

    def test_duplicate_package_is_rejected(self):
        line='(1/1) Upgrading curl (1 -> 2)'
        with self.assertRaises(ValueError):m.parse_changes('alpine',line+'\n'+line)


if __name__=='__main__':unittest.main()
