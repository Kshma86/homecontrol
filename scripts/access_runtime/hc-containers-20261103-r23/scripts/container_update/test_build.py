import importlib.util
from pathlib import Path
import unittest

s=importlib.util.spec_from_file_location('container_build',Path(__file__).with_name('build.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class InventoryDeltas(unittest.TestCase):
    def test_native_multiarch_name_matches_apt_plan(self):
        self.assertEqual(m.inventory_difference('debian','linux-libc-dev:amd64\t1\nother\t3\n','linux-libc-dev:amd64\t2\nother\t3\n'),
                         [{'package':'linux-libc-dev','installed':'1','candidate':'2'}])

    def test_other_package_change_or_removal_remains_visible(self):
        self.assertEqual(m.inventory_difference('debian','a\t1\nb\t2\n','a\t1\n'),
                         [{'package':'b','installed':'2','candidate':None}])

    def test_alpine_exact_inventory_delta(self):
        self.assertEqual(m.inventory_difference('alpine','libexpat-1-r0\nmusl-1-r0\n','libexpat-2-r0\nmusl-1-r0\n'),
                         {'removed':['libexpat-1-r0'],'added':['libexpat-2-r0']})

    def test_ambiguous_architecture_inventory_is_rejected(self):
        with self.assertRaises(ValueError):m.inventory_difference('debian','a\t1\na:amd64\t1\n','a\t2\n')


if __name__=='__main__':unittest.main()
