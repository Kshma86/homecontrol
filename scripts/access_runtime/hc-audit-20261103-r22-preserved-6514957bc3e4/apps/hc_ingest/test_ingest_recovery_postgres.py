"""Opt-in HC-11 real MQTT/Postgres recovery in a network-isolated disposable lab.

The host lab runner handles request-{stop,start} files for its own DB only.
Never accepts a production DSN, broker, or Docker socket.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest

import paho.mqtt.client as mqtt
import psycopg2


@unittest.skipUnless(os.getenv('HC11_RECOVERY_LAB') == '1', 'requires isolated HC-11 lab')
class IngestRecoveryTest(unittest.TestCase):
    def test_actual_main_outage_recovery_order_debounce_and_shutdown_flush(self):
        evidence = Path('/evidence')
        dsn = 'host=127.0.0.1 dbname=hc11_recovery_test user=postgres'
        def connect():
            c = psycopg2.connect(dsn, connect_timeout=1);c.autocommit = True
            return c
        conn = connect();self.addCleanup(conn.close)
        def sql(statement, params=(), one=False):
            with conn.cursor() as cur:
                cur.execute(statement, params)
                return cur.fetchone() if one else None
        with conn.cursor() as cur:
            cur.execute('select current_database()');self.assertEqual(cur.fetchone()[0], 'hc11_recovery_test')
            cur.execute((Path(__file__).resolve().parents[2]/'infra/db/baselines/hc_r1_058_v1.sql').read_text())
            cur.execute((Path(__file__).resolve().parents[2]/'infra/db/062_hc33_ingest_sample_identity.sql').read_text())
        sql("create role hc_app login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls")
        sql('revoke create on database hc11_recovery_test from public')
        sql('revoke create on schema public from public')
        sql('grant usage on schema hc to hc_app')
        sql('grant select,insert,update,delete on all tables in schema hc to hc_app')
        sql('grant usage,select on all sequences in schema hc to hc_app')
        device = sql("insert into hc.device(platform,name) values('zigbee','lab') returning id", one=True)[0]
        eid = sql("insert into hc.entity(device_id,name,topic_base) values(%s,'lab','zigbee/hc11-fixture') returning id", (device,), True)[0]
        sql("insert into hc.metric(key,value_type,enforce_validation) values('temperature','num',false),('contact','bool',false),('hc33_history','num',false)")
        sql("insert into hc.entity_metric(entity_id,metric_key,store_mode,deadband_num,min_interval_sec) values(%s,'temperature','both',0,0),(%s,'contact','both',null,0)", (eid,eid))
        sql("insert into hc.entity_metric(entity_id,metric_key,store_mode,deadband_num,min_interval_sec) values(%s,'hc33_history','history',0,0)",(eid,))
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect('127.0.0.1',1883,60);client.loop_start()
        self.addCleanup(client.disconnect);self.addCleanup(client.loop_stop)
        def emit(payload, retain=False):
            result=client.publish('zigbee/hc11-fixture',json.dumps(payload),qos=1,retain=retain)
            result.wait_for_publish(2);self.assertTrue(result.is_published())
        def wait(predicate, timeout=10):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                try:
                    if predicate():return
                except (OSError,ValueError,psycopg2.Error):pass
                time.sleep(.025)
            raise AssertionError('lab condition timeout')
        status_path=Path('/tmp/hc_ingest_status.json')
        def status():return json.loads(status_path.read_text())
        app_log=(evidence/'actual-main.log').open('w')
        self.addCleanup(app_log.close)
        environment={**os.environ,'MQTT_HOST':'127.0.0.1','PG_HOST':'127.0.0.1','PG_USER':'hc_app','PG_DB':'hc11_recovery_test','PG_PASSWORD':'','HEARTBEAT_WRITE_INTERVAL_SECONDS':'1','INGEST_DB_CONNECT_TIMEOUT_SECONDS':'1','INGEST_DB_RETRY_SECONDS':'.2','INGEST_SHUTDOWN_TIMEOUT_SECONDS':'1','CONTACT_DEBOUNCE_SECONDS':'.5','INGEST_MEASUREMENT_MAX_ATTEMPTS':'30','INGEST_INBOX_MAX_MESSAGES':'8','INGEST_INBOX_MAX_BYTES':'4096'}
        # Shorter sweep only in lab; real persistence/parsers/callbacks unchanged.
        process=subprocess.Popen([sys.executable,'-u','-c','import mqtt_ingest_multi as m; m.SWEEP_EVERY_SECONDS=.5; raise SystemExit(m.main())'],env=environment,stdout=app_log,stderr=subprocess.STDOUT)
        self.addCleanup(lambda:process.kill() if process.poll() is None else None)
        wait(lambda:status()['db_ready'] and status()['mqtt_connected'])
        emit({'contact':True});wait(lambda:sql("select v_bool from hc.entity_state where key='contact'",one=True)==(True,))
        emit({'contact':False});time.sleep(.1);emit({'contact':True});time.sleep(.7)
        self.assertEqual(sql("select v_bool from hc.entity_state where key='contact'",one=True),(True,))
        emit({'contact':False});time.sleep(.2)
        self.assertEqual(sql("select v_bool from hc.entity_state where key='contact'",one=True),(True,))
        wait(lambda:sql("select v_bool from hc.entity_state where key='contact'",one=True)==(False,))
        for value in range(10,20):emit({'temperature':value});time.sleep(.04)
        wait(lambda:sql("select v_num from hc.entity_state where key='temperature'",one=True)==(19.,))
        wait(lambda:sql("select count(*) from hc.measurement where key='temperature'",one=True)[0]==10)
        # Candidate must not survive a failed DB session.
        emit({'contact':True,'hc33_history':91});time.sleep(.12)
        (evidence/'request-stop').touch();wait(lambda:(evidence/'done-stop').exists())
        for value in range(1000,1100):emit({'temperature':value});time.sleep(.015)
        wait(lambda:not status()['db_ready'] and status()['inbox']['dropped'].get('db_unavailable',0)>=90)
        down=status();heartbeat=float(Path('/tmp/hc_ingest_heartbeat').stat().st_mtime)
        time.sleep(1.1)
        self.assertGreater(Path('/tmp/hc_ingest_heartbeat').stat().st_mtime,heartbeat)
        self.assertTrue(status()['mqtt_connected']);self.assertIsNone(process.poll())
        self.assertLessEqual(down['inbox']['high_water_messages'],8)
        self.assertGreater(down['connect_attempts'],1)
        self.assertGreaterEqual(down['contact_candidates_dropped'],1)
        conn.close();(evidence/'request-start').touch();wait(lambda:(evidence/'done-start').exists())
        wait(lambda:status()['db_ready']);conn=connect();self.addCleanup(conn.close)
        self.assertEqual(sql("select v_bool from hc.entity_state where key='contact'",one=True),(False,))
        self.assertEqual(sql("select count(*) from hc.measurement where v_num>=1000",one=True),(0,))
        self.assertEqual(sql("select count(*) from hc.measurement where key='hc33_history' and v_num=91",one=True),(1,))
        self.assertEqual(sql("select count(*) from hc.entity_state where key='hc33_history'",one=True),(0,))
        for value in range(30,35):emit({'temperature':value});time.sleep(.06)
        wait(lambda:sql("select v_num from hc.entity_state where key='temperature'",one=True)==(34.,))
        emit({'contact':True});wait(lambda:sql("select v_bool from hc.entity_state where key='contact'",one=True)==(True,))
        emit({'temperature':35});wait(lambda:sql("select v_num from hc.entity_state where key='temperature'",one=True)==(35.,))
        before_shutdown=time.time()
        emit({'hc33_history':92})
        wait(lambda:float(sql('select extract(epoch from last_seen_ts) from hc.entity_presence',one=True)[0])>before_shutdown)
        time.sleep(.05)
        process.send_signal(signal.SIGTERM);self.assertEqual(process.wait(4),0)
        self.assertEqual(sql("select count(*) from hc.measurement where key='hc33_history'",one=True),(2,))
        rows=[]
        with conn.cursor() as cur:
            cur.execute("select v_num,meta,extract(epoch from ts) from hc.measurement where key='temperature' order by ts,ctid")
            rows=cur.fetchall()
        self.assertEqual([r[0] for r in rows],list(range(10,20))+list(range(30,36)))
        self.assertTrue(all(r[1]['retained'] is False and 0<=float(r[2])-r[1]['recv_ts']<6 for r in rows))
        self.assertEqual(sql("select count(*) from hc.measurement where key='contact'",one=True)[0],3)
        # A real new process must warm history and suppress a processed unchanged live sample.
        sql("update hc.entity_metric set deadband_num=1,min_interval_sec=0,max_interval_sec=300 where metric_key='temperature'")
        process=subprocess.Popen([sys.executable,'-u','-c','import mqtt_ingest_multi as m; m.SWEEP_EVERY_SECONDS=.5; raise SystemExit(m.main())'],env=environment,stdout=app_log,stderr=subprocess.STDOUT)
        wait(lambda:status()['db_ready'] and status()['mqtt_connected'])
        emit({'temperature':35})
        wait(lambda:status()['inbox']['processing_attempts']>=1)
        self.assertEqual(sql("select count(*) from hc.measurement where key='temperature'",one=True),(16,))
        emit({'temperature':36})
        wait(lambda:sql("select v_num from hc.entity_state where key='temperature'",one=True)==(36.,))
        process.send_signal(signal.SIGTERM);self.assertEqual(process.wait(4),0)
        self.assertEqual(sql("select count(*) from hc.measurement where key='temperature'",one=True),(17,))
        self.assertEqual(sql("select count(*) from hc.measurement where key='hc33_history'",one=True),(2,))
        summary={'accepted_history_recovered':True,'shutdown_flushed_history_only_sample':True,'actual_process_restart_preserved_history_deadband':True,'outage':down,'ordered_temperature_values':[r[0] for r in rows], 'contact_bounce_suppressed':True,'contact_candidate_dropped_at_failure':True,'no_outage_replay':True,'mqtt_and_heartbeat_continue':True,'shutdown_exit_code':process.returncode,'shutdown_saved_last_sample':True,'device_network':False}
        (evidence/'postgres-integration.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':unittest.main()
