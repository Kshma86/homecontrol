import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from mower_motor_test import MotorTestService
from mower_motor_test_routes import register_motor_test_routes
from mower_operator_auth import COOKIE_NAME, MowerOperatorAuth
from mower_v3_service import MowerV3Service
from tests.test_mower_motor_test import Transport, INITIAL
from werkzeug.security import generate_password_hash

ROOT = '/api/mower/v3/motor-test'


class MotorTestRoutesTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.rover = MowerV3Service(transport=self.transport, read_only=True, motor_test_enabled=True)
        self.service = MotorTestService(self.rover, type('Manual', (), {'active':False})())
        self.auth = MowerOperatorAuth(password_hash=generate_password_hash('test-only', method='pbkdf2:sha256:1000'), secret='ab'*32)
        app = Flask(__name__)
        register_motor_test_routes(app, service=self.service, auth=self.auth)
        self.client = app.test_client()
        self.body = dict(v=3,request_id='apply-1',esp_boot=self.transport.identity['esp_boot'],stm_boot=self.transport.identity['stm_boot'],
                         control_epoch=3,expected_revision=0,parameters=INITIAL)

    def login(self):
        self.client.set_cookie(COOKIE_NAME, self.auth.login('test-only')[0], path='/api/mower/v3')

    def post(self, raw=None, origin='http://localhost'):
        return self.client.post(ROOT+'/apply', data=raw or json.dumps(self.body,separators=(',',':')),content_type='application/json',headers={'Origin':origin})

    def test_initial_draft_public_no_mutation_all_native_operations_authenticated(self):
        response = self.client.get(ROOT+'/initial')
        self.assertEqual(response.json['validation']['parameters_crc'],'27384620')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.get(ROOT+'/status').status_code,401)
        self.assertEqual(self.client.get(ROOT+'/reconcile').status_code,401)
        self.assertEqual(self.post().status_code,401)
        self.assertEqual(self.transport.calls,[])
        self.assertEqual(self.transport.posts,[])

    def test_origin_duplicates_floats_missing_or_extra_fields_reject_before_transport(self):
        self.login()
        self.assertEqual(self.post(origin='https://evil.test').status_code,403)
        for raw in ('{"v":3,"v":3}', json.dumps(self.body | {'parameters': INITIAL | {'wheel_track_mm':290.0}}),
                    json.dumps(self.body | {'force':True}), 'x'*2049):
            self.assertEqual(self.post(raw).status_code,400)
        self.assertEqual(self.transport.posts,[])

    def test_authenticated_apply_202_then_exact_get_only_reconciliation(self):
        self.login()
        response = self.post()
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.json['result'],'PENDING')
        self.transport.activate()
        args = dict(request_id='apply-1',esp_boot=self.body['esp_boot'],stm_boot=self.body['stm_boot'],expected_revision=1,parameters_crc='27384620')
        result = self.client.get(ROOT+'/reconcile',query_string=args)
        self.assertEqual(result.json['result'],'APPLIED')
        self.assertEqual(len(self.transport.posts),1)
        self.assertEqual(self.transport.posts[0][0],'/api/v3/parameters')

    def test_single_superuser_needs_no_login_and_saves_one_config(self):
        self.auth.superuser = True
        response = self.client.post(ROOT+'/config', json={'parameters':INITIAL}, headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['saved'])
        self.assertEqual(self.client.get(ROOT+'/config').json['parameters'],INITIAL)
        self.assertEqual(self.post().status_code,202)
        self.assertEqual(self.post(origin='https://evil.test').status_code,403)



if __name__ == '__main__': unittest.main()
