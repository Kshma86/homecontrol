import copy
import unittest
import rover_parameters as codec
from mower_parameters_service import validate_draft
from mower_motor_test import MotorTestService
from mower_manual_service import ManualSession, claim_ready
from mower_v3_service import MowerV3Service, RoverReadError, RoverHttp
from tests.test_mower_motor_test import Transport, INITIAL

class Simplify11Tests(unittest.TestCase):
    def test_compact_10_and_13_roundtrip_and_replacement(self):
        for enabled in (False, True):
            full = copy.deepcopy(INITIAL)
            full['blade_enabled'] = enabled
            compact = codec.necessary(full)
            self.assertEqual(len(compact), 13 if enabled else 10)
            decoded = codec.decode(codec.encode(compact))
            self.assertEqual(codec.necessary(decoded), compact)
            self.assertEqual(decoded['wheel_track_mm'], 0)
            if not enabled:
                self.assertEqual(decoded['blade_erpm_limit'], 0)
                self.assertEqual(decoded['motor_accel_erpm_s'][2], 0)
            self.assertTrue(validate_draft(compact)['valid'])
            with self.assertRaises(ValueError): codec.validate(compact | {'guess': 1})
            with self.assertRaises(ValueError): codec.validate(compact | {'wheel_direction': [0,1]})

    def test_disarmed_claim_with_third_offline_uses_new_epoch_and_zero_third(self):
        transport = Transport()
        transport.activate()
        transport.identity.update(manual_claim_from_disarmed=True, minimal_erpm_parameters=True)
        transport.state.update(stopped=False)
        snapshot = MowerV3Service(transport=transport, simple_control=True, motor_test_enabled=True, clock=lambda:100).snapshot()
        self.assertTrue(claim_ready(snapshot))
        self.assertTrue(snapshot['identity']['manual_claim_from_disarmed'])
        session = ManualSession(snapshot, clock=lambda:100)
        session.client(dict(type='claim', request_id='direct-claim', esp_boot=snapshot['identity']['esp_boot'], stm_boot=snapshot['identity']['stm_boot'], control_epoch=4),100)
        session.server(dict(type='claimed', lease_id=7, control_epoch=5, lease_ms=350, max_linear_mm_s=0, max_yaw_mdeg_s=0, drive_mode='ERPM', motor_erpm_limits=[1000,1000,0]))
        frame = dict(type='drive_erpm',lease_id=7,control_epoch=5,seq=1,left_erpm=100,right_erpm=-100,third_erpm=0,deadman=True)
        session.client(frame,100)
        for updates in ({'seq':2,'third_erpm':1},{'seq':2,'control_epoch':4},{'seq':2,'deadman':False}):
            with self.assertRaises(RoverReadError): session.client(frame | updates,100)
        self.assertEqual(transport.posts,[])
        snapshot['state']['state']='FAULT'
        self.assertFalse(claim_ready(snapshot))
        snapshot['state']['state']='DISARMED'
        snapshot['identity']['manual_claim_from_disarmed']=False
        self.assertFalse(claim_ready(snapshot))

    def test_uart_recovery_disables_claim_but_old_counters_do_not(self):
        transport = Transport()
        transport.activate()
        transport.identity['manual_claim_from_disarmed'] = True
        rover = MowerV3Service(transport=transport,simple_control=True,motor_test_enabled=True,clock=lambda:100)
        self.assertTrue(rover.snapshot()['capabilities']['manual'])
        transport.recovering = True
        self.assertFalse(rover.snapshot()['capabilities']['manual'])
        transport.recovering = False
        self.assertTrue(rover.snapshot()['capabilities']['manual'])
        self.assertEqual(transport.posts,[])

    def test_compact_apply_is_single_send_and_saved_as_compact(self):
        transport = Transport()
        rover = MowerV3Service(transport=transport,simple_control=True,motor_test_enabled=True,clock=lambda:100)
        service = MotorTestService(rover, type('Manual', (), {'active':False})())
        compact = codec.necessary(INITIAL | {'blade_enabled':False})
        body = dict(v=3,request_id='compact-apply',esp_boot=transport.identity['esp_boot'],stm_boot=transport.identity['stm_boot'],control_epoch=3,expected_revision=0,parameters=compact)
        result, status = service.apply(body)
        self.assertEqual(status,202)
        self.assertEqual(result['result'],'PENDING')
        self.assertEqual(len(transport.posts),1)
        self.assertEqual(transport.posts[0][1]['parameters'],compact)
        self.assertEqual(result['parameters_crc'],f'{codec.checksum(compact):08X}')

    def test_health_path_is_supported_by_real_transport(self):
        transport = RoverHttp('http://192.168.1.119', 'ab'*32)
        calls=[]
        transport._exchange=lambda method,path,*args: (calls.append((method,path)) or (200,{'v':3}))
        self.assertEqual(transport.get('/api/v3/health'),{'v':3})
        self.assertEqual(calls,[('GET','/api/v3/health')])

    def test_optional_manual_ws_stack_measurement_is_diagnostic_only(self):
        transport=Transport();transport.activate();transport.identity['manual_claim_from_disarmed']=True
        original=transport.get
        for value in (None,5100):
            transport.get=lambda path: original(path) | ({'esp_stack_min_bytes':{'manual_ws':value}} if path=='/api/v3/health' else {})
            snapshot=MowerV3Service(transport=transport,simple_control=True,motor_test_enabled=True,clock=lambda:100).snapshot()
            self.assertEqual(snapshot['health']['esp_stack_min_bytes']['manual_ws'],value)
            self.assertTrue(snapshot['capabilities']['manual'])
