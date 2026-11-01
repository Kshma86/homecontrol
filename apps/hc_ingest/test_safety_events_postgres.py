"""Opt-in ingest -> PostgreSQL -> worker integration, never a device network."""
import os
from pathlib import Path
import sys
import time
import unittest
from urllib.parse import urlparse

import mqtt_ingest_multi as ingest


@unittest.skipUnless(os.environ.get('HC06_SLEEP_TEST_POSTGRES') == '1', 'requires disposable sleeping-sensor DB')
class SleepingSafetyPostgresTest(unittest.TestCase):
    def setUp(self):
        import psycopg2
        from psycopg2.extras import RealDictCursor
        url = os.environ['HC06_SLEEP_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc06_sleeping_test':
            raise AssertionError('requires dedicated local hc06_sleeping_test database')
        self.conn = psycopg2.connect(url)
        self.addCleanup(self.conn.close)
        with self.conn.cursor() as cur:
            cur.execute('select current_database()')
            if cur.fetchone()[0] != 'hc06_sleeping_test':
                raise AssertionError('connection resolved to another database')
            cur.execute('drop schema if exists hc cascade')
            cur.execute((Path(__file__).resolve().parents[2] / 'infra/db/baselines/hc_r1_058_v1.sql').read_text())
            cur.execute((Path(__file__).resolve().parents[2] / 'infra/db/062_hc33_ingest_sample_identity.sql').read_text())
        self.conn.commit()
        self.conn.autocommit = True
        self.cursor_factory = RealDictCursor
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'infra/backend'))
        from combustion_safety_service import CombustionSafetyService
        self.execute("insert into hc.combustion_safety_config(singleton,enabled) values(true,true)")
        self.execute('insert into hc.combustion_safety_runtime(singleton) values(true)')
        self.ids = {}
        for key in ('extractor','co','smoke'):
            device = self.one("insert into hc.device(platform,ext_id,name) values('system',%s,%s) returning id", (key,key))['id']
            self.ids[key] = self.one('insert into hc.entity(device_id,name,topic_base) values(%s,%s,%s) returning id', (device,key,'fixture/'+key))['id']
        ingest.last_saved.clear()
        ingest.last_saved_retained.clear()
        ingest.pending_measurements.clear()
        self.addCleanup(ingest.last_saved.clear)
        self.addCleanup(ingest.last_saved_retained.clear)
        self.addCleanup(ingest.pending_measurements.clear)
        self.emit('extractor','power',0,'num')
        self.emit('co','carbon_monoxide',False,'bool')
        self.emit('co','carbon_monoxide_value',0,'num')
        self.emit('co','fault',False,'bool')
        self.emit('smoke','smoke',False,'bool')
        self.execute("update hc.entity_state set ts=now()-interval '180 days' where entity_id in(%s,%s)", (self.ids['co'],self.ids['smoke']))
        self.radio = dict(co=True,smoke=True,extractor=True)
        self.publications = []
        self.service = CombustionSafetyService(
            self.all, self.one, self.one,
            lambda topic,payload: self.publications.append((topic,payload)) or (True,'lab fake transport'),
            lambda key: {'combustion_co_sensor':self.ids['co'], 'combustion_smoke_sensor':self.ids['smoke'],
                         'combustion_extractor':self.ids['extractor'], 'combustion_indicator':None}[key],
            lambda ext: {'radio_online':self.radio.get(ext)},
        )

    def execute(self, sql, params=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)

    def all(self, sql, params=()):
        with self.conn.cursor(cursor_factory=self.cursor_factory) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def one(self, sql, params=()):
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def emit(self, sensor, key, value, vtype, *, retained=False):
        entity = self.ids[sensor]
        rule = ingest.Rule('both', 1 if vtype=='num' else None, 3600, 86400, True)
        self.execute('insert into hc.entity_metric(entity_id,metric_key) values(%s,%s) on conflict do nothing',(entity,key))
        now = time.time()
        if not ingest.should_write(entity,key,value,rule,now,retained=retained,co_sensor=sensor=='co')[0]:
            return False
        meta = dict(src='mqtt',retained=retained,topic='fixture/'+sensor,recv_ts=now)
        with self.conn.cursor() as cur:
            ingest.upsert_entity_state(cur,entity,key,vtype,value,meta)
            ingest.queue_measurement(entity,key,vtype,value,meta)
            if ingest.flush_measurements(cur) != 1:
                raise AssertionError('history did not receive the event')
        ingest.update_last(entity,key,value,now,retained=retained)
        return True

    def test_sleep_then_smoke_alarm_clear_radio_loss_and_numeric_co_crossing(self):
        before = self.all('select entity_id,key,ts from hc.entity_state where entity_id in(%s,%s) order by entity_id,key', (self.ids['co'],self.ids['smoke']))
        with self.conn.cursor() as cur:
            ingest.warm_last_saved_from_entity_state(cur)
        # Simulate retained reconnect delivery after max_interval; no state or
        # provenance rewrite, including a replay that differs from recorded state.
        ingest.last_saved[self.ids['co'],'carbon_monoxide_value'] = (0,time.time()-86401)
        self.assertFalse(self.emit('co','carbon_monoxide_value',0,'num',retained=True))
        self.assertFalse(self.emit('smoke','smoke',False,'bool',retained=True))
        result = self.service.tick()
        self.assertTrue(result['input_health']['co'])
        self.assertTrue(result['input_health']['smoke'])
        self.assertTrue(result['latched'])
        self.assertFalse(self.service.acknowledge()['latched'])
        self.assertEqual(before, self.all('select entity_id,key,ts from hc.entity_state where entity_id in(%s,%s) order by entity_id,key', (self.ids['co'],self.ids['smoke'])))
        self.assertTrue(self.emit('smoke','smoke',True,'bool'))
        self.assertTrue(self.service.tick()['danger'])
        self.assertTrue(self.one('select latched from hc.combustion_safety_runtime')['latched'])
        with self.assertRaises(ValueError): self.service.acknowledge()
        self.assertTrue(self.emit('smoke','smoke',False,'bool'))
        self.assertTrue(self.service.tick()['latched'])
        self.radio['smoke'] = False
        with self.assertRaises(ValueError): self.service.acknowledge()
        self.radio['smoke'] = True
        self.assertFalse(self.service.acknowledge()['latched'])
        self.assertTrue(self.emit('co','carbon_monoxide_value',19.9,'num'))
        self.service.tick()
        self.assertTrue(self.emit('co','carbon_monoxide_value',20.1,'num'))
        self.assertTrue(self.service.tick()['danger'])
        with self.assertRaises(ValueError): self.service.acknowledge()
        self.assertTrue(self.emit('co','carbon_monoxide_value',0,'num'))
        self.assertFalse(self.service.tick()['danger'])
        self.assertFalse(self.service.acknowledge()['latched'])
        self.assertIsNotNone(self.one('select acknowledged_at from hc.combustion_safety_runtime')['acknowledged_at'])
        # Retained positive evidence still latches; a retained clear cannot
        # erase it. A real live clear is accepted despite the minimum interval.
        self.assertTrue(self.emit('smoke','smoke',True,'bool',retained=True))
        self.assertTrue(self.service.tick()['danger'])
        with self.assertRaises(ValueError): self.service.acknowledge()
        self.assertFalse(self.emit('smoke','smoke',False,'bool',retained=True))
        self.assertTrue(self.emit('smoke','smoke',False,'bool'))
        self.assertFalse(self.service.tick()['danger'])
        self.assertFalse(self.service.acknowledge()['latched'])
        # First retained clear is unknown, then same-valued live delivery is a
        # valid confirmation (not trapped by the prior retained cache entry).
        self.execute("delete from hc.entity_state where entity_id=%s and key='smoke'", (self.ids['smoke'],))
        ingest.last_saved.pop((self.ids['smoke'],'smoke'))
        ingest.last_saved_retained.pop((self.ids['smoke'],'smoke'))
        self.assertTrue(self.emit('smoke','smoke',False,'bool',retained=True))
        self.assertFalse(self.service.tick()['input_health']['smoke'])
        with self.assertRaises(ValueError): self.service.acknowledge()
        self.assertTrue(self.emit('smoke','smoke',False,'bool'))
        self.assertTrue(self.service.tick()['input_health']['smoke'])
        self.assertFalse(self.service.acknowledge()['latched'])
        self.assertFalse(self.publications)  # No indicator; extractor already off.


if __name__ == '__main__':
    unittest.main()
