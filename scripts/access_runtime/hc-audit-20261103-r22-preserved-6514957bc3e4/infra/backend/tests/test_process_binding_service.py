import unittest
from unittest.mock import Mock

from process_binding_service import ProcessBindingService


def service():
    return ProcessBindingService(*(Mock() for _ in range(4)),
        normalize_text=lambda value: str(value).strip(),
        api_cache_delete_prefix=Mock(), invalidate_context=Mock())


def entity(entity_id=11, **changes):
    return dict(entity_id=entity_id, entity_name='socket', device_id=1,
        platform='zigbee', topic_base='test/socket',
        metrics=['switch_state','power'], **changes)


class ProcessBindingTest(unittest.TestCase):
    def binding(self, stored, fallback=None, key='climate_extra_fan_socket'):
        obj=service()
        obj.stored_binding=Mock(return_value=stored)
        obj.fallback_entity=Mock(return_value=fallback)
        return obj, obj.binding(key)

    def test_initial_legacy_fallback_is_preserved(self):
        obj,payload=self.binding(None,entity(22))
        self.assertEqual(payload['configuration_state'],'not_configured')
        self.assertTrue(payload['uses_fallback'])
        self.assertEqual(obj.selected_entity_id('climate_extra_fan_socket'),22)

    def test_explicit_valid_binding_wins(self):
        obj,payload=self.binding(entity(),entity(22))
        self.assertEqual(payload['configuration_state'],'valid')
        self.assertEqual(payload['selected_entity_id'],11)
        self.assertFalse(payload['uses_fallback'])
        obj.fallback_entity.assert_not_called()

    def test_invalid_explicit_binding_never_uses_fallback(self):
        variants=[dict(entity_id=11,entity_name=None),dict(entity_id=None),
                  {**entity(),'device_id':None}, {**entity(),'metrics':['power']},
                  {**entity(),'metrics':[]}, {**entity(),'platform':'unsupported'},
                  {**entity(),'metrics':['switch_state','contact']}]
        for stored in variants:
            with self.subTest(stored=stored):
                obj,payload=self.binding(stored,entity(22))
                self.assertEqual(payload['configuration_state'],'invalid')
                self.assertIsNone(payload['selected_entity_id'])
                self.assertFalse(payload['uses_fallback'])
                self.assertIsNone(obj.selected_topic_base('climate_extra_fan_socket'))
                obj.fallback_entity.assert_not_called()

    def test_missing_or_invalid_fallback_is_unavailable(self):
        for fallback in (None,{**entity(),'metrics':['power']}):
            obj,payload=self.binding(None,fallback)
            self.assertIsNone(payload['selected_entity'])
            self.assertEqual(payload['configuration_state'],'not_configured')
            self.assertFalse(payload['uses_fallback'])

    def test_extractor_needs_switch_and_power_indicator_needs_colour_controls(self):
        obj=service()
        self.assertIsNone(obj.invalid_reason('combustion_extractor',entity()))
        self.assertEqual(obj.invalid_reason('combustion_extractor',{**entity(),'metrics':['switch_state']}),'power_capability_unavailable')
        self.assertEqual(obj.invalid_reason('combustion_indicator',entity()),'indicator_capability_unavailable')

    def test_read_only_live_binding_inventory_remains_usable(self):
        # The deployed eleven role assignments have these relevant capabilities.
        obj=service()
        metrics={'combustion_extractor':['switch_state','power'],
                 'combustion_indicator':['switch_state','brightness','color'],
                 'combustion_co_sensor':['carbon_monoxide'],
                 'combustion_smoke_sensor':['smoke'],
                 'irrigation_soil_moisture':['soil_moisture'],
                 'marten_power_socket':['switch_state','power_w'],
                 'marten_motion_sensor':['occupancy'],
                 'climate_extra_fan_socket':['switch_state','power'],
                 'climate_power_meter':['power_w','energy_kwh'],
                 'ai_node_power_plug':['switch_state','power_w'],
                 'hc_server_power_meter':['power_w','energy_kwh']}
        for key,keys in metrics.items():
            with self.subTest(key=key):
                self.assertIsNone(obj.invalid_reason(key,{**entity(),'metrics':keys}))


class BindingConsumerTest(unittest.TestCase):
    def test_ai_cannot_reuse_raw_config_when_binding_is_unavailable(self):
        from ai_node_service import AiNodeService
        obj=object.__new__(AiNodeService)
        obj.power_entity_id='22'
        obj.process_binding_entity_id=lambda key:None
        self.assertEqual(obj.active_power_entity_id(),'')
        obj.process_binding_entity_id=None
        self.assertEqual(obj.active_power_entity_id(),'22')

    def test_climate_and_server_meters_do_not_query_a_replacement(self):
        from climate_service import ClimateService
        from energy_device_service import EnergyDeviceService
        for cls,method in ((ClimateService,'power_meter_payload'),(EnergyDeviceService,'server_power_history_payload')):
            with self.subTest(service=cls):
                obj=object.__new__(cls)
                obj.process_binding_entity_id=lambda key:None
                obj.power_meter_ext_id='legacy'
                obj.fetch_one=Mock(side_effect=AssertionError('legacy replacement queried'))
                self.assertFalse(getattr(obj,method)()['ok'])
                obj.fetch_one.assert_not_called()

    def test_soil_binding_none_reaches_weather_as_unknown(self):
        from tests.test_irrigation_service import IrrigationServiceTest
        obj=IrrigationServiceTest().service()
        obj.fetch_pilot_config=Mock(return_value={'soil_sensor_topic_base':'legacy'})
        obj.process_binding_topic=lambda key:None
        class StopAfterResolution(Exception):pass
        obj.build_weather_snapshot=Mock(side_effect=StopAfterResolution)
        with self.assertRaises(StopAfterResolution):obj.evaluate_pilot()
        obj.build_weather_snapshot.assert_called_once_with(None)


if __name__=='__main__':unittest.main()
