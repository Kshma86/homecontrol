"""Service-side admission failures must never reach physical OPEN."""
import unittest

from tests import test_irrigation_service as fixtures


class IrrigationAdmissionTest(unittest.TestCase):
    def service(self, **options):
        service = fixtures.IrrigationServiceTest().service(**options)
        service.evaluate_pilot = lambda **kw: {'mode': 'navigator', 'final_duration': 5, 'reason': 'fixture'}
        service.v2_stop_policy = lambda *a: {}
        service.fetch_one = lambda *a: {'id': 7, 'duration_minutes': 5, 'label': 'test'}
        service.running_session = lambda: None
        service.log_pilot_decision = lambda *a, **kw: None
        return service

    def test_rejected_manual_reservation_returns_conflict_without_open(self):
        service = self.service(reserve_session=lambda **kw: {'session': None, 'blocked_by': 'active_session'})
        service.execute_one = lambda *a: self.fail('losing start wrote session state')
        payload, status = service.start_manual({'duration_minutes': 5})
        self.assertEqual(status, 409)
        self.assertEqual(payload['blocked_by'], 'active_session')
        self.assertEqual(service.published, [])

    def test_rejected_scheduled_reservation_does_not_publish_or_advance_day(self):
        service = self.service(reserve_session=lambda **kw: {'session': None, 'blocked_by': 'schedule_not_due'})
        service.execute_one = lambda *a: self.fail('losing scheduler advanced state')
        service.mark_v2_execution = lambda *a: self.fail('losing scheduler reported execution')
        service.start_v2_scheduled_session(7)
        self.assertEqual(service.published, [])

    def test_missing_transactional_dependency_fails_closed(self):
        for method, arg in (('start_manual', {}), ('start_v2_scheduled_session', 7)):
            with self.subTest(method=method):
                service = self.service(reserve_session=None)
                with self.assertRaisesRegex(RuntimeError, 'admission is not configured'):
                    getattr(service, method)(arg)
                self.assertEqual(service.published, [])

    def test_reservation_exception_never_authorizes_open(self):
        def unavailable(**kw):
            raise TimeoutError('reservation result unknown')
        for method, arg in (('start_manual', {}), ('start_v2_scheduled_session', 7)):
            with self.subTest(method=method):
                service = self.service(reserve_session=unavailable)
                with self.assertRaises(TimeoutError):
                    getattr(service, method)(arg)
                self.assertEqual(service.published, [])

    def test_manual_cannot_impersonate_physical_observation(self):
        service = self.service(reserve_session=lambda **kw: self.fail('physical origin admitted'))
        payload, status = service.start_manual({'started_by': 'physical_manual'})
        self.assertEqual(status, 400)
        self.assertFalse(payload['ok'])
        self.assertEqual(service.published, [])

    def test_manual_reserves_clamped_duration_and_committed_row_before_open(self):
        calls = []
        def reserve(**kw):
            calls.append(kw)
            return {'session': {'id': 5}}
        service = self.service(reserve_session=reserve)
        service.execute_one = lambda *a: {'id': 5, 'status': 'running'}
        def opened(*args, **kw):
            self.assertEqual(len(calls), 1)
            return True, 'confirmed', {}
        service.publish_open_with_confirmation = opened
        payload, status = service.start_manual({'duration_minutes': 999})
        self.assertEqual(status, 200)
        self.assertEqual(calls[0]['minutes'], 180)
        self.assertEqual(calls[0]['safety_minutes'], 180)
        self.assertEqual(calls[0]['started_by'], 'admin')
        self.assertIsNone(calls[0]['schedule_id'])


if __name__ == '__main__':
    unittest.main()
