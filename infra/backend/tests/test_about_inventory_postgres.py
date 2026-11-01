"""Opt-in HC-48 regression checks on a disposable local PostgreSQL database."""
import os
import unittest
from urllib.parse import urlparse

from system_status_service import SystemStatusService


@unittest.skipUnless(os.environ.get('HC48_TEST_POSTGRES') == '1', 'requires isolated HC-48 PostgreSQL')
class AboutInventoryPostgresTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        url = os.environ['HC48_TEST_DATABASE_URL']
        parsed = urlparse(url)
        if parsed.hostname != '127.0.0.1' or parsed.path != '/hc48_inventory_test':
            raise AssertionError('requires dedicated local hc48_inventory_test database')
        self.conn = psycopg.connect(url, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        # Minimal inventory schema: actual production query, synthetic rows.
        self.conn.execute('''
            create schema if not exists hc;
            create table if not exists hc.device (
              id int primary key, platform text, model text, manufacturer text,
              name text, location text, is_active bool);
            create table if not exists hc.entity (id int primary key, device_id int, is_active bool);
            create table if not exists hc.entity_metric (entity_id int, metric_key text, is_enabled bool);
            truncate hc.entity_metric, hc.entity, hc.device;
            insert into hc.device values
              (1,'zigbee','Many',null,'One','Garden',true),
              (2,'zigbee','Pair',null,'Two',null,true),
              (3,'zigbee','Pair',null,'Three',null,true),
              (4,'zigbee','Empty',null,'Four',null,true),
              (5,'zigbee','None',null,'Five',null,true),
              (6,'zigbee','Many',null,'Inactive',null,false);
            insert into hc.entity values
              (11,1,true),(12,1,true),(13,1,false),(21,2,true),
              (22,3,true),(41,4,true),(61,6,true);
            insert into hc.entity_metric values
              (11,'temperature',true),(11,'humidity',true),(11,'battery',true),
              (12,'temperature',true),(13,'humidity',true),(13,'linkquality',true),
              (13,'soil_moisture',false),(21,'temperature',true),
              (22,'temperature',true),(61,'ghost',true);
            ''')
        self.conn.commit()
        self.queries = []
        self.service = object.__new__(SystemStatusService)
        def fetch(sql, params=(), many=False):
            self.queries.append(sql)
            cursor = self.conn.execute(sql, params)
            return cursor.fetchall() if many else cursor.fetchone()
        self.service.fetch_one = fetch
        self.service.fetch_all = lambda sql, params=(): fetch(sql, params, many=True)
        self.conn.execute('set transaction read only')

    def inventory(self):
        result = self.service.about_inventory_stats()
        self.assertEqual(len(self.queries), 4)
        self.assertEqual(set(result), {'devices', 'entities', 'sensor_types', 'metric_types'})
        return result

    def test_counts_follow_device_entity_identity_despite_metric_fanout(self):
        rows = {row['type']: row for row in self.inventory()['sensor_types']}
        self.assertEqual({key: (row['device_count'], row['entity_count']) for key, row in rows.items()},
                         {'Many': (1, 3), 'Pair': (2, 2), 'Empty': (1, 1), 'None': (1, 0)})
        self.assertEqual(rows['Many']['metrics'], ['battery', 'humidity', 'linkquality', 'temperature'])
        self.assertEqual(rows['Many']['capabilities'], ['Temperature / humidity', 'Battery / link'])
        self.assertEqual(rows['None']['metrics'], [])

    def test_existing_active_filters_summaries_and_metric_counts_are_preserved(self):
        result = self.inventory()
        # Existing contract: active devices, all their entities (even inactive);
        # metric_types separately filters active entities and enabled metrics.
        self.assertEqual(result['devices'], dict(devices_total=6, devices_active=5, platform_count=1, model_count=4))
        self.assertEqual(result['entities'], dict(entities_total=7, entities_active=6))
        self.assertEqual({row['metric_key']: row['entity_count'] for row in result['metric_types']},
                         {'temperature': 4, 'humidity': 1, 'battery': 1, 'ghost': 1})
        many = next(row for row in result['sensor_types'] if row['type'] == 'Many')
        self.assertEqual(many['examples'], 'One')
        self.assertEqual(many['locations'], 'Garden')

    def test_ordering_uses_device_count_instead_of_number_of_metrics(self):
        rows = self.inventory()['sensor_types']
        self.assertEqual([row['type'] for row in rows], ['Pair', 'Empty', 'Many', 'None'])


if __name__ == '__main__':
    unittest.main()
