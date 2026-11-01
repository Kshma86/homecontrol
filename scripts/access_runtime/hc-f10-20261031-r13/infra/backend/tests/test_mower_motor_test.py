import copy
import json
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rover_parameters as codec
from mower_motor_test import MotorTestService, motor_identity
from mower_manual_service import ManualSession
from mower_parameters_service import DraftError, MowerParametersService
from mower_v3_service import MowerV3Service, RoverReadError, UnknownMutation
from tests.test_mower_v3_service import identity, state
from tests.test_mower_parameters import MemoryStore

INITIAL = json.loads((Path(__file__).resolve().parents[1] / 'static/rover_motor_test.initial.json').read_text())


class Transport:
    def __init__(self):
        self.identity = identity() | dict(mode='MOTOR_TEST', esp_fw='esp-motor-test-20261012', stm_fw='stm-motor-test-20261012',
            profile_crc='4D545331', commissioned=False, profile_verified=False, motion_permitted=False,
            stm_remote_update=False, stm_image_max_bytes=0, esp_ota_max_bytes=0, esp_ota_enabled=False,
            autonomous_enabled=False, stm_flash_layout='H743_1M_STANDALONE', runtime_parameters=True,
            parameter_versions_supported=[1, 2], manual_erpm=False, test_manual_control=False,
            # A missing updater service can still report locked ERROR; explicit test gates decide.
            update_locked=True)
        self.state = state() | dict(fault_mask='00000000', safety_installed_mask=None, safety_active_mask=None,
            safety_source_valid=False, safety_source_seq=0, safety_source_age_ms=None)
        self.parameters = dict(v=3, parameters_version=1, esp_boot=self.identity['esp_boot'], stm_boot=self.identity['stm_boot'],
            control_epoch=3, revision=0, request_id=None, parameters_crc=None, storage='EMPTY', busy=False, available=True,
            source_valid=True, source_age_ms=10, can_apply=True, applied=False, code='EMPTY', parameters=None,
            commissioned=False, motion_permitted=False)
        self.posts = []
        self.calls = []
        self.lost = False

    def get(self, path):
        self.calls.append(path)
        if path == '/api/v3/health':
            return dict(v=3, esp_boot=self.identity['esp_boot'], uart_recovering=getattr(self,'recovering',False),
                        uart_rx_closed=False, stm_peer_alive=True, uart_recovery_attempts=100, uart_recovery_completed=100)
        return copy.deepcopy({'/api/v3/identity': self.identity, '/api/v3/state': self.state,
                              '/api/v3/parameters': self.parameters}[path])

    def request(self, method, path, body=None):
        if method == 'GET':
            return 200, self.get(path)
        self.posts.append((path, copy.deepcopy(body)))
        if self.lost:
            raise UnknownMutation()
        return 202, dict(v=3, request_id=body['request_id'], result='PENDING', code='QUEUED')

    def activate(self, id_='apply-1'):
        self.parameters.update(parameters_version=2, storage='ACTIVE', revision=1, request_id=id_, parameters_crc='27384620',
                               parameters=copy.deepcopy(INITIAL), applied=True, code='APPLIED', control_epoch=4)
        self.state.update(control_epoch=4, source_seq=16, state_seq=15)
        self.identity.update(manual_erpm=True, test_manual_control=True)


class MotorTestTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.rover = MowerV3Service(transport=self.transport, read_only=False, motor_test_enabled=True, simple_control=True, clock=lambda: 100)
        self.manual = type('Manual', (), dict(active=False))()
        self.service = MotorTestService(self.rover, self.manual)
        self.body = dict(v=3, request_id='apply-1', esp_boot=self.transport.identity['esp_boot'],
                         stm_boot=self.transport.identity['stm_boot'], control_epoch=3, expected_revision=0, parameters=copy.deepcopy(INITIAL))

    def correlation(self):
        return {key: self.body[key] for key in ('request_id', 'esp_boot', 'stm_boot')} | dict(expected_revision=1, parameters_crc='27384620')

    def test_reference_rcp2_roundtrip_crc_and_hc_draft(self):
        self.assertEqual(codec.checksum(INITIAL), 0x27384620)
        self.assertEqual(codec.decode(codec.encode(INITIAL)), INITIAL)
        service = MowerParametersService(MemoryStore())
        saved = service.save('motor-test', dict(request_id='save-1', expected_revision=0, parameters=INITIAL))
        self.assertTrue(saved['validation']['valid'])
        self.assertFalse(saved['apply_available'])
        self.assertEqual(json.loads(service.export('motor-test', 1)), INITIAL)

    def test_initial_read_is_passive(self):
        self.transport.identity["test_manual_control"] = True
        self.assertTrue(self.rover.snapshot()['capabilities']['manual'])
        self.assertEqual(self.transport.posts, [])

    def test_unknown_reply_has_no_pending_lock_or_128_limit(self):
        self.transport.lost = True
        for index in range(130):
            self.assertEqual(self.service.apply(self.body | {'request_id': f'apply-{index}'})[0]['result'], 'UNKNOWN')
        self.assertEqual(len(self.transport.posts), 130)
        self.assertIsNone(self.service.pending_info())
        self.transport.activate()
        self.assertEqual(self.service.reconcile(self.correlation())['result'], 'APPLIED')
        self.assertEqual(len(self.transport.posts), 130)

    def test_old_pending_ignored_and_single_config_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'pending.json'
            old.write_text('{"pending":"old"}')
            config = Path(directory) / 'config.json'
            service = MotorTestService(self.rover, self.manual, config_path=config, pending_path=old)
            service.save_configuration(INITIAL)
            restarted = MotorTestService(self.rover, self.manual, config_path=config, pending_path=old)
            self.assertEqual(restarted.configuration()['parameters'], INITIAL)
            self.assertIsNone(restarted.pending_info())
            restarted.apply(self.body)
            self.assertEqual(len(self.transport.posts), 1)

    def test_native_readiness_and_firmware_names_do_not_gate_hc(self):
        for target, updates in [('identity', {'esp_fw':'new-build','profile_crc':'00000000'}),
                                ('state', {'stopped':False})]:
            self.setUp()
            getattr(self.transport,target).update(updates)
            with self.subTest(target=target):
                self.assertEqual(self.service.apply(self.body)[0]['result'],'PENDING')
                self.assertEqual(len(self.transport.posts),1)

    def test_current_epoch_and_compatible_connection_required(self):
        with self.assertRaises(DraftError): self.service.apply(self.body | {'control_epoch':2})
        self.assertEqual(self.transport.posts,[])
        self.transport.identity['compatible']=False
        with self.assertRaises(DraftError): self.service.apply(self.body)
        self.assertEqual(self.transport.posts,[])

    def test_motor_session_limits_full_snapshot_false_deadman_and_metric_rejected(self):
        self.transport.activate()
        self.transport.state.update(state='IDLE', armed=True)
        session = ManualSession(self.rover.snapshot(), clock=lambda:100)
        session.client(dict(type='claim', request_id='claim-1', esp_boot=self.body['esp_boot'], stm_boot=self.body['stm_boot'], control_epoch=4),100)
        session.server(dict(type='claimed', lease_id=7, control_epoch=5, lease_ms=350,
                            max_linear_mm_s=0, max_yaw_mdeg_s=0, drive_mode='ERPM', motor_erpm_limits=[1000,1000,1000]))
        frame = dict(type='drive_erpm', lease_id=7, control_epoch=5, seq=1, left_erpm=100, right_erpm=-100, third_erpm=1000, deadman=True)
        session.client(frame,100)
        for update in ({'seq':2,'third_erpm':1001},{'seq':2,'deadman':False},{'seq':2,'left_erpm':True},{'seq':2,'extra':0}):
            with self.assertRaises(RoverReadError): session.client(frame | update,100)
        with self.assertRaises(RoverReadError):
            session.client(dict(type='drive', lease_id=7, control_epoch=5, seq=2, linear_mm_s=0,yaw_mdeg_s=0,blade_rpm=0,deadman=True),100)
        session.client(frame | dict(seq=2,left_erpm=0,right_erpm=0,third_erpm=0,deadman=False),100)
        session.client(dict(type='stop',lease_id=7,control_epoch=5,seq=3),100)
        session.client(dict(type='release',lease_id=7,control_epoch=5),100)
        with self.assertRaises(RoverReadError): session.client(frame | dict(seq=4),100)

    def test_independent_safe_timestamps_do_not_renew_state_or_break_repeated_reads(self):
        self.transport.activate()
        first = self.rover.snapshot()
        self.transport.state.update(safety_source_seq=1, safety_source_age_ms=5, safety_source_valid=True,
                                    safety_installed_mask='00000007', safety_active_mask='00000000')
        second = self.rover.snapshot()
        self.assertTrue(second['freshness']['fresh'])
        self.assertEqual(second['state']['safety_installed_mask'], 7)

    def test_native_command_paths_only_arm_disarm_reset_and_reserved_stop(self):
        self.transport.activate()
        for command in ('start','resume','heading_set','pause'):
            value = {'heading_mdeg':0} if command=='heading_set' else {'mission_id':'12345678-1234-1234-1234-123456789abc','revision':1,'crc32':'27384620'} if command in ('start','resume') else None
            result, status = self.rover.command_service().submit(dict(v=3,request_id=command,esp_boot=self.body['esp_boot'],stm_boot=self.body['stm_boot'],control_epoch=4,command=command,value=value))
            self.assertEqual(status,409)
        self.assertEqual(self.transport.posts, [])
        result, status = self.rover.command_service().submit(dict(v=3,request_id='stop-1'),stop=True)
        self.assertEqual(self.transport.posts[0][0], '/api/v3/stop')


if __name__ == '__main__': unittest.main()
