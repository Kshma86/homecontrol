import copy
import unittest
import rover_parameters as codec
from mower_motor_test import MotorTestService, validate_parameters_status
from mower_parameters_service import DraftError
from mower_v3_service import MowerV3Service, RoverReadError
from tests.test_mower_motor_test import Transport, INITIAL

class ParameterStorageTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.transport.activate()
        self.transport.parameters.update(stored_parameters_valid=True, stored_parameters=copy.deepcopy(INITIAL))
        self.rover = MowerV3Service(transport=self.transport,simple_control=True,motor_test_enabled=True,clock=lambda:100)
        self.service = MotorTestService(self.rover,type('Manual',(),{'active':False})())
        self.body=dict(v=3,request_id='save-change',esp_boot=self.transport.identity['esp_boot'],stm_boot=self.transport.identity['stm_boot'],control_epoch=4,expected_revision=1,parameters=copy.deepcopy(INITIAL))

    def change(self):
        self.body['parameters']['wheel_brake_ma'][0] += 1

    def test_editor_open_uses_stored_not_hc_cache_and_writes_nothing(self):
        cache=copy.deepcopy(INITIAL);cache['wheel_brake_ma'][0]+=20
        self.service.save_configuration(cache)
        result=self.service.configuration()
        self.assertEqual(result['source'],'rover_stored')
        self.assertEqual(result['parameters'],INITIAL)
        self.assertEqual(result['canonical_rcp'],codec.encode(INITIAL).hex())
        self.assertEqual(self.transport.posts,[])

    def test_stored_remains_visible_offline_or_pending_without_applied_claim(self):
        self.transport.parameters.update(storage='PENDING',applied=False,can_apply=False,source_valid=False,source_age_ms=None,parameters=None)
        self.transport.state['source_valid']=False
        result=self.service.configuration()
        self.assertEqual(result['source'],'rover_stored')
        self.assertEqual(result['parameters'],INITIAL)
        self.assertFalse(result['rover_status']['applied'])
        self.assertFalse(result['rover_status']['can_apply'])
        self.assertEqual(self.transport.posts,[])

    def test_identical_reordered_and_rebooted_config_do_not_write(self):
        self.body['parameters']=dict(reversed(list(INITIAL.items())))
        result,status=self.service.apply(self.body)
        self.assertEqual(result['result'],'UNCHANGED')
        self.assertEqual(status,200)
        for target in (self.transport.identity,self.transport.state,self.transport.parameters):
            target.update(esp_boot='1111111111111111',stm_boot='2222222222222222')
        self.body.update(esp_boot='1111111111111111',stm_boot='2222222222222222')
        self.assertEqual(self.service.apply(self.body)[0]['result'],'UNCHANGED')
        self.assertEqual(self.transport.parameters['revision'],1)
        self.assertEqual(self.transport.posts,[])

    def test_change_sends_once_and_requires_native_confirmation(self):
        self.change()
        result,status=self.service.apply(self.body)
        self.assertEqual(result['result'],'PENDING')
        self.assertEqual(len(self.transport.posts),1)
        receipt=dict(request_id='save-change',esp_boot=self.body['esp_boot'],stm_boot=self.body['stm_boot'],expected_revision=2,parameters_crc=result['parameters_crc'])
        self.assertEqual(self.service.reconcile(receipt)['result'],'UNKNOWN')
        self.transport.parameters.update(revision=2,request_id='save-change',parameters_crc=result['parameters_crc'],parameters=self.body['parameters'],stored_parameters=self.body['parameters'])
        self.assertEqual(self.service.reconcile(receipt)['result'],'APPLIED')
        self.assertEqual(len(self.transport.posts),1)

    def test_conflict_or_native_cannot_apply_never_posts(self):
        self.change()
        self.body['expected_revision']=0
        with self.assertRaises(DraftError) as error:self.service.apply(self.body)
        self.assertEqual(error.exception.code,'CONFIG_CONFLICT')
        self.body['expected_revision']=1
        self.transport.parameters.update(can_apply=False,storage='PENDING',applied=False,parameters=None)
        with self.assertRaises(DraftError) as error:self.service.apply(self.body)
        self.assertEqual(error.exception.code,'CONFIG_NOT_READY')
        self.assertEqual(self.transport.posts,[])

    def test_legacy_applied_fallback_and_null_retains_display_cache(self):
        self.transport.parameters.pop('stored_parameters_valid')
        self.transport.parameters.pop('stored_parameters')
        self.assertEqual(self.service.configuration()['source'],'rover_applied')
        self.transport.parameters.update(parameters=None,applied=False,storage='PENDING')
        result=self.service.configuration()
        self.assertEqual(result['source'],'hc_cache')
        self.assertEqual(result['parameters'],INITIAL)
        self.assertEqual(self.transport.posts,[])

    def test_invalid_stored_crc_or_validity_cannot_be_rover_source(self):
        self.transport.parameters['stored_parameters']['wheel_brake_ma'][0]+=1
        with self.assertRaises(RoverReadError):validate_parameters_status(self.transport.parameters)
        self.transport.parameters.update(stored_parameters=None)
        with self.assertRaises(RoverReadError):validate_parameters_status(self.transport.parameters)
