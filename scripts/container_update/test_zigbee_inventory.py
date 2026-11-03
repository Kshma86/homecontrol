import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

spec=importlib.util.spec_from_file_location('bounded_zigbee',Path(__file__).with_name('zigbee_inventory.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class BoundedInventory(unittest.TestCase):
    def setUp(self):
        self.namespace={'__name__':'test'};exec(compile(m.PROBE_CODE,'bounded_inventory','exec'),self.namespace)
        self.decode=self.namespace['decode_topic'];self.topic='zigbee/bridge/devices'

    def test_large_device_definition_is_accepted_without_exposing_definitions(self):
        data=[{'ieee_address':'0x'+format(n,'016x'),'definition':{'description':'x'*3500}} for n in range(58)]
        payload=json.dumps(data).encode();self.assertGreater(len(payload),65536)
        result=self.decode(payload,self.topic)
        self.assertEqual(len(result),58);self.assertTrue(all(len(v)==18 for v in result))

    def test_oversized_message_is_rejected_before_json_decoding(self):
        with self.assertRaisesRegex(ValueError,'bound'):self.decode(b'x'*(2*1024**2+1),self.topic)

    def test_duplicate_and_incomplete_inventory_fail_closed(self):
        for values in ([],[{'ieee_address':'0x0000000000000001'}],
                       [{'ieee_address':'0x0000000000000001'}]*2,[{},{}]):
            with self.subTest(values=values),self.assertRaises(ValueError):self.decode(json.dumps(values).encode(),self.topic)

    def test_unexpected_topic_is_rejected(self):
        with self.assertRaises(ValueError):self.decode(b'{}','zigbee/#')

    def test_version_mismatch_cannot_satisfy_activation(self):
        e=Mock();e.call.return_value='{"version":"2.8.0","identities":["one","two"]}'
        with self.assertRaisesRegex(ValueError,'version'):m.bridge(e,'2.14.3')


if __name__=='__main__':unittest.main()
