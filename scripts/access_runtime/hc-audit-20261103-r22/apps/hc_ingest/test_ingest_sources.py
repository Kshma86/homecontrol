import unittest
import mqtt_ingest_multi as m


class SourceMappingTest(unittest.TestCase):
    def test_tuya_state_and_per_metric_current_stay_current_a(self):
        for topic,payload in [('homecontrol/tele/tuya/poller/plug/state',{'current_a':1.25}),
                              ('homecontrol/tele/tuya/poller/plug/m/current_a',1.25),
                              ('homecontrol/tele/tuya/plug/state',{'current_a':1.25}),
                              ('homecontrol/tele/tuya/plug/m/current_a',1.25)]:
            with self.subTest(topic=topic):
                items=m.tuya_metric_items(topic,payload)
                self.assertEqual([(m.map_key(k,v,topic),v) for k,v,_ in items],[('current_a',1.25)])
    def test_irrigation_aliases_are_scoped_to_actual_telemetry(self):
        aliases={'pump':'pump_running','current_a':'pump_current_a','voltage_12v':'supply_voltage_12v',
                 'temp_c':'controller_temp_c','valve':'valve_state','manual_valve':'manual_valve_state'}
        for key,target in aliases.items():
            with self.subTest(key=key):
                self.assertEqual(m.map_key(key,1,'homecontrol/tele/irrigation/controller/pump_metrics'),target)
                for topic in ('zigbee/plug','homecontrol/tele/tuya/plug/state','homecontrol/tele/growatt/inverter/state',
                              'other/solar','homecontrol/tele/irrigation//pump_metrics'):
                    self.assertEqual(m.map_key(key,1,topic),key)
    def test_solar_and_valve_motor_normalized_keys_are_preserved(self):
        self.assertEqual(m.map_key('pv_current',2,'homecontrol/tele/irrigation/controller/solar'),'solar_pv_current_a')
        self.assertEqual(m.map_key('pv_current',2,'other/solar'),'pv_current')
        for key in ('valve_current_a','motor_current_ma','pump_current_a','current_a'):
            self.assertEqual(m.map_key(key,2,'homecontrol/tele/tuya/plug/state'),key)
        self.assertEqual(m.map_key('valve_current_a',1.2,'homecontrol/tele/irrigation/controller/pump_metrics'),'valve_current_a')
    def test_generic_energy_switch_and_voltage_mapping_is_unchanged(self):
        for raw,value,key in [('energy',1,'energy_kwh'),('switch',True,'switch_state'),
                              ('voltage',230,'mains_voltage_v'),('voltage',3000,'battery_voltage_mv')]:
            self.assertEqual(m.map_key(raw,value,'zigbee/fixture'),key)
