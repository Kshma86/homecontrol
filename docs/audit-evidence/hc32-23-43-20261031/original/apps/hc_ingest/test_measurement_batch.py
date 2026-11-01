import time
import unittest
from unittest.mock import patch
from psycopg2 import OperationalError, DataError
from measurement_batch import Measurement, MeasurementQueue


def sample(value=1):
    return Measurement(1,'temperature',(value,None,None,None),{'retained':False},value,time.time())


class QueueTest(unittest.TestCase):
    def test_count_bytes_and_oversize_reject_newest(self):
        m=sample();q=MeasurementQueue(2,m.size*2)
        self.assertTrue(q.append(m));self.assertTrue(q.append(sample(2)))
        self.assertFalse(q.append(sample(3)));self.assertEqual(q.status()['dropped']['overflow'],1)
        q=MeasurementQueue(max_bytes=1);self.assertFalse(q.append(m))
        self.assertEqual(q.status()['dropped']['oversize'],1)
    def test_age_and_retry_bounds_are_counted(self):
        q=MeasurementQueue(max_age=1,max_attempts=2);old=sample();old.enqueued-=2
        retry=sample();retry.attempts=2
        q.append(old);q.append(retry);q.expire()
        self.assertEqual(len(q),0);self.assertEqual(q.status()['dropped'],{'expired':1,'retry_exhausted':1})
    def test_connection_error_preserves_identity_and_cache_without_row_fallback(self):
        q=MeasurementQueue();m=sample();confirmed=[];m.confirm=lambda:confirmed.append(True);q.append(m)
        class Cursor:
            def execute(self,*args):pass
        with patch('measurement_batch.execute_values',side_effect=OperationalError('fixture connection lost')) as insert:
            with self.assertRaises(OperationalError):q.flush(Cursor())
        self.assertEqual(insert.call_count,1);self.assertEqual(q.items,[m]);self.assertFalse(confirmed)
        self.assertEqual(m.attempts,1)
    def test_queue_only_removed_after_confirmed_commit(self):
        q=MeasurementQueue();m=sample();q.append(m);events=[]
        class Cursor:
            def execute(self,sql):
                if sql=='COMMIT':self_outer.assertEqual(q.items,[m]);events.append('commit')
        self_outer=self;m.apply_state=lambda cur:events.append('state');m.confirm=lambda:events.append('cache')
        with patch('measurement_batch.execute_values',return_value=[(m.sample_id,)]):self.assertEqual(q.flush(Cursor()),1)
        self.assertEqual(events,['state','commit','cache']);self.assertEqual(len(q),0)
    def test_default_retry_limit_stops_after_three_failed_flushes(self):
        q=MeasurementQueue();q.append(sample())
        class Cursor:
            def execute(self,sql):pass
        with patch('measurement_batch.execute_values',side_effect=OperationalError('fixture down')) as insert:
            for _ in range(3):
                with self.assertRaises(OperationalError):q.flush(Cursor())
            self.assertEqual(q.flush(Cursor()),0)
        self.assertEqual(insert.call_count,3)
        self.assertEqual(q.status()['dropped']['retry_exhausted'],1)
        self.assertEqual(len(q),0)
    def test_unknown_commit_preserves_queue_then_duplicate_does_not_repeat_state(self):
        q=MeasurementQueue();m=sample();q.append(m);states=[];m.apply_state=lambda cur:states.append(1)
        class Cursor:
            fail=True
            def execute(self,sql):
                if sql=='COMMIT' and self.fail:self.fail=False;raise OperationalError('lost commit response')
        cur=Cursor()
        with patch('measurement_batch.execute_values',side_effect=[[(m.sample_id,)],[]]):
            with self.assertRaises(OperationalError):q.flush(cur)
            self.assertEqual(len(q),1);self.assertEqual(q.flush(cur),1)
        self.assertEqual(states,[1]);self.assertEqual(q.status()['duplicate_confirmations'],1)
    def test_invalid_config_rejected(self):
        for kw in ({'max_messages':0},{'max_bytes':0},{'max_age':0},{'max_age':float('nan')},{'max_attempts':0}):
            with self.assertRaises(ValueError):MeasurementQueue(**kw)


if __name__=='__main__':unittest.main()
