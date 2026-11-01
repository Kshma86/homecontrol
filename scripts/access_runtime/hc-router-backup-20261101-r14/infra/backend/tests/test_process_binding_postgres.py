"""Opt-in HC-35/36 tests. Dedicated internal-network PostgreSQL only."""
from contextlib import contextmanager
import os
import threading
import time
import unittest
from urllib.parse import urlparse

from climate_fan_coordination import ClimateFanCoordinator
from process_binding_service import ProcessBindingService
from power_wall_service import PowerWallService


@unittest.skipUnless(os.getenv('HC3536_TEST_POSTGRES')=='1','requires disposable HC-35/36 PostgreSQL')
class ProcessBindingPostgresTest(unittest.TestCase):
    def setUp(self):
        from database_service import DatabaseService
        from psycopg.rows import dict_row
        url=os.environ['HC3536_TEST_DATABASE_URL']
        parsed=urlparse(url)
        assert parsed.hostname=='hc3536-postgres' and parsed.path=='/hc3536_test'
        self.db=DatabaseService(url)
        self.coord=lambda:ClimateFanCoordinator(lambda:self.db.conn(dict_row))
        self.db.execute_sql('''create schema if not exists hc;
          create table if not exists hc.device(id bigint primary key, name text, platform text,
            ext_id text, location text, model text, manufacturer text, is_active boolean default true);
          create table if not exists hc.entity(id bigint primary key, device_id bigint references hc.device,
            name text, topic_base text, is_active boolean default true);
          create table if not exists hc.entity_metric(entity_id bigint references hc.entity on delete cascade,
            metric_key text, is_enabled boolean default true);
          create table if not exists hc.process_sensor_binding(process_key text primary key,
            entity_id bigint references hc.entity on delete set null, updated_at timestamptz default now());
          create table if not exists hc.power_wall_policy(entity_id bigint primary key references hc.entity on delete cascade,
            display_name text, auto_climate boolean default false, auto_climate_delay_minutes int default 3,
            auto_climate_on_at timestamptz, updated_at timestamptz default now(), last_action_at timestamptz,
            last_action text, last_error text, always_on boolean default false, scheduler_enabled boolean default false);
          create table if not exists hc.power_wall_schedule_session(entity_id bigint, status text);
          truncate hc.device, hc.entity, hc.entity_metric, hc.process_sensor_binding,
            hc.power_wall_policy, hc.power_wall_schedule_session;
          insert into hc.device(id,name,platform,ext_id) values(1,'A','zigbee','a'),(2,'B','zigbee','b'),(3,'C','zigbee','c');
          insert into hc.entity values(11,1,'A','test/a',true),(22,2,'B','test/b',true),(33,3,'C','test/c',true);
          insert into hc.entity_metric(entity_id,metric_key) select id,k from hc.entity cross join unnest(array['power','switch_state']) k;
          insert into hc.power_wall_policy(entity_id,auto_climate) values(11,true),(22,false),(33,false);
          insert into hc.process_sensor_binding(process_key,entity_id) values('climate_extra_fan_socket',11);
          insert into hc.power_wall_schedule_session values(33,'planned');''')
        self.binding=self.make_binding()
        self.calls=[]
        self.power=self.make_power()

    def make_binding(self):
        obj=ProcessBindingService(self.db.fetch_all,self.db.fetch_one,self.db.execute_one,self.db.execute_sql,
             lambda x:str(x).strip(),lambda *a:None,lambda *a:None,climate_fan_coordinator=self.coord())
        obj._schema_ready=True
        return obj

    def make_power(self):
        obj=PowerWallService(self.db.fetch_all,self.db.fetch_one,self.db.execute_one,lambda *a:None,
            lambda:None,lambda *a:None,lambda *a:None,lambda *a:None,lambda x,default='':str(x or default),30,
            process_binding_entity_id=self.binding.selected_entity_id,climate_fan_coordinator=self.coord())
        obj.publish_switch=lambda row,target,source:(self.calls.append((row['entity_id'],target)) or (True,'fake','test',{}))
        obj.command_entity=lambda entity_id:self.db.fetch_one('select id as entity_id from hc.entity where id=%s',(entity_id,))
        return obj

    def pending(self,entity_id=11,interval="-1 second"):
        self.db.execute_sql('update hc.power_wall_policy set auto_climate_on_at=now()+%s::interval where entity_id=%s',(interval,entity_id))

    def policies(self):
        return self.db.fetch_all('select entity_id, auto_climate, auto_climate_on_at from hc.power_wall_policy order by entity_id')

    def test_missing_binding_keeps_legacy_fallback(self):
        self.db.execute_sql('delete from hc.process_sensor_binding')
        row=self.binding.binding('climate_extra_fan_socket')
        self.assertEqual((row['configuration_state'],row['selected_entity_id'],row['uses_fallback']),('not_configured',11,True))

    def test_missing_legacy_fallback_stays_unavailable(self):
        self.db.execute_sql('delete from hc.process_sensor_binding;update hc.entity set is_active=false where id=11')
        row=self.binding.binding('climate_extra_fan_socket')
        self.assertEqual(row['configuration_state'],'not_configured')
        self.assertIsNone(row['selected_entity_id'])
        self.assertFalse(row['uses_fallback'])
        self.power.sync_auto_climate('on')
        self.assertEqual(self.calls,[])

    def test_normalized_process_key_still_uses_atomic_climate_handover(self):
        self.pending()
        self.binding.set_binding(' climate_extra_fan_socket ',22)
        self.assertEqual(self.binding.selected_entity_id('climate_extra_fan_socket'),22)
        self.assertEqual(self.db.fetch_one('select count(*) n from hc.process_sensor_binding')['n'],1)
        self.assertIsNone(self.policies()[0]['auto_climate_on_at'])

    def test_inactive_entity_device_and_disabled_metric_never_choose_b(self):
        self.db.execute_sql('update hc.power_wall_policy set auto_climate=true where entity_id=22')
        for sql in ('update hc.entity set is_active=false where id=11',
                    'update hc.device set is_active=false where id=1',
                    "update hc.entity_metric set is_enabled=false where entity_id=11 and metric_key='switch_state'"):
            with self.subTest(sql=sql):
                self.db.execute_sql(sql)
                row=self.binding.binding('climate_extra_fan_socket')
                self.assertEqual(row['configuration_state'],'invalid')
                self.assertIsNone(row['selected_entity_id'])
                self.assertFalse(row['uses_fallback'])
                self.pending()
                self.power.sync_auto_climate('on');self.power.climate_delay_tick()
                self.assertEqual(self.calls,[])
                self.db.execute_sql('update hc.entity set is_active=true;update hc.device set is_active=true;update hc.entity_metric set is_enabled=true')

    def test_entity_deletion_null_does_not_look_unconfigured(self):
        self.db.execute_sql('delete from hc.entity where id=11;update hc.power_wall_policy set auto_climate=true where entity_id=22')
        row=self.binding.binding('climate_extra_fan_socket')
        self.assertIsNone(row['stored_entity_id'])
        self.assertEqual(row['configuration_state'],'invalid')
        self.assertIsNone(row['selected_entity_id'])

    def test_invalid_candidate_rejected(self):
        self.db.execute_sql("update hc.entity_metric set is_enabled=false where entity_id=22 and metric_key='switch_state'")
        with self.assertRaises(ValueError):self.binding.set_binding('climate_extra_fan_socket',22)
        self.assertEqual(self.binding.selected_entity_id('climate_extra_fan_socket'),11)

    def test_a_pending_binding_b_off_tick_never_publishes_a_on(self):
        self.pending()
        self.binding.set_binding('climate_extra_fan_socket',22)
        self.power.sync_auto_climate('off');self.power.climate_delay_tick()
        self.assertEqual(self.calls,[(22,False)])
        self.assertEqual(self.policies()[0]['auto_climate'],False)
        self.assertIsNone(self.policies()[0]['auto_climate_on_at'])

    def test_a_b_a_cannot_restore_old_pending(self):
        self.pending();self.binding.set_binding('climate_extra_fan_socket',22)
        self.power.sync_auto_climate('on')
        self.binding.set_binding('climate_extra_fan_socket',11)
        self.power.climate_delay_tick()
        self.assertEqual(self.calls,[])
        self.assertTrue(all(row['auto_climate_on_at'] is None for row in self.policies()))

    def test_same_binding_preserves_valid_own_delay_and_repeated_on_does_not_extend(self):
        self.pending(interval='5 minutes')
        at=self.policies()[0]['auto_climate_on_at']
        self.binding.set_binding('climate_extra_fan_socket',11)
        self.power.sync_auto_climate('on')
        self.assertEqual(self.policies()[0]['auto_climate_on_at'],at)

    def test_off_before_binding_change_does_not_start_new_target(self):
        self.pending();self.power.sync_auto_climate('off')
        self.binding.set_binding('climate_extra_fan_socket',22)
        self.power.climate_delay_tick()
        self.assertEqual(self.calls,[(11,False)])

    def test_new_target_has_own_delay_and_unrelated_jobs_survive(self):
        self.pending();self.binding.set_binding('climate_extra_fan_socket',22)
        self.power.sync_auto_climate('on')
        self.assertIsNotNone(self.policies()[1]['auto_climate_on_at'])
        self.pending(22);self.power.climate_delay_tick()
        self.assertEqual(self.calls,[(22,True)])
        self.assertEqual(self.db.fetch_one('select * from hc.power_wall_schedule_session')['status'],'planned')

    def test_restart_old_a_pending_cannot_run_with_current_b(self):
        self.binding.set_binding('climate_extra_fan_socket',22)
        self.pending(11);self.pending(22,'5 minutes')
        at=self.policies()[1]['auto_climate_on_at']
        self.make_power().climate_delay_tick()
        self.assertEqual(self.calls,[])
        self.assertIsNone(self.policies()[0]['auto_climate_on_at'])
        self.assertEqual(self.policies()[1]['auto_climate_on_at'],at)

    def test_policy_disable_blocks_due_on(self):
        self.pending();self.power.set_policy(11,auto_climate_marker=False)
        self.power.climate_delay_tick()
        self.assertEqual(self.calls,[])
        self.assertIsNone(self.policies()[0]['auto_climate_on_at'])

    def test_zero_delay_and_manual_off_cancel_pending(self):
        self.db.execute_sql('update hc.power_wall_policy set auto_climate_delay_minutes=0 where entity_id=11')
        self.pending();self.power.sync_auto_climate('on');self.power.sync_auto_climate('off')
        self.power.climate_delay_tick()
        self.assertEqual(self.calls,[(11,True),(11,False)])

    def test_failed_binding_transaction_rolls_back_binding_policy_and_intent(self):
        self.pending();before=self.policies()
        original=self.binding.climate_fan_coordinator.locked
        @contextmanager
        def failed():
            with original() as cur:
                yield cur
                raise RuntimeError('injected before commit')
        self.binding.climate_fan_coordinator.locked=failed
        with self.assertRaisesRegex(RuntimeError,'injected'):
            self.binding.set_binding('climate_extra_fan_socket',22)
        self.assertEqual(self.binding.selected_entity_id('climate_extra_fan_socket'),11)
        self.assertEqual(self.policies(),before)

    def test_tuya_tab_manual_off_cancels_the_same_fan_intent(self):
        self.pending()
        self.db.execute_sql("update hc.device set platform='tuya' where id=1")
        self.power.tuya_command_entity=lambda **kw:self.db.fetch_one(
            'select id as entity_id, name as entity_name from hc.entity where id=%s',(kw['entity_id'],))
        self.power.publish_mqtt=lambda topic,payload:(self.calls.append((payload['entity_id'],payload['value'])) or (True,'fake'))
        self.power.tuya_switch_command(11,'A',False)
        self.power.climate_delay_tick()
        self.assertEqual(self.calls,[(11,False)])
        self.assertIsNone(self.policies()[0]['auto_climate_on_at'])

    def start(self,callback):
        errors=[]
        def run():
            try:callback()
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=run)
        thread.start()
        return thread,errors

    def finish(self,thread,errors):
        thread.join(8)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])

    def test_tick_publish_orders_before_concurrent_binding_and_off(self):
        self.pending()
        publishing,release,changed=threading.Event(),threading.Event(),threading.Event()
        original=self.power.publish_switch
        def publish(*args):
            publishing.set()
            if not release.wait(5):raise AssertionError('publisher not released')
            return original(*args)
        self.power.publish_switch=publish
        tick,errors=self.start(self.power.climate_delay_tick)
        try:
            self.assertTrue(publishing.wait(5))
            def change():
                self.binding.set_binding('climate_extra_fan_socket',22);changed.set()
            setter,set_errors=self.start(change)
            self.assertFalse(changed.wait(.15))
        finally:release.set()
        self.finish(tick,errors);self.finish(setter,set_errors)
        self.power.sync_auto_climate('off');self.power.climate_delay_tick()
        self.assertEqual(self.calls,[(11,True),(22,False)])

    def test_uncommitted_binding_is_atomic_and_tick_waits_for_commit(self):
        self.pending()
        written,release,ran=threading.Event(),threading.Event(),threading.Event()
        original=self.binding.climate_fan_coordinator.locked
        @contextmanager
        def pause_before_commit():
            with original() as cur:
                yield cur
                written.set()
                if not release.wait(5):raise AssertionError('commit not released')
        self.binding.climate_fan_coordinator.locked=pause_before_commit
        setter,errors=self.start(lambda:self.binding.set_binding('climate_extra_fan_socket',22))
        try:
            self.assertTrue(written.wait(5))
            self.assertEqual(self.binding.selected_entity_id('climate_extra_fan_socket'),11)
            self.assertTrue(self.policies()[0]['auto_climate'])
            self.assertIsNotNone(self.policies()[0]['auto_climate_on_at'])
            def tick():self.power.climate_delay_tick();ran.set()
            worker,worker_errors=self.start(tick)
            self.assertFalse(ran.wait(.15))
        finally:release.set()
        self.finish(setter,errors);self.finish(worker,worker_errors)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.binding.selected_entity_id('climate_extra_fan_socket'),22)

    def test_lock_timeout_is_bounded_and_publishes_nothing(self):
        self.pending()
        with self.coord().locked():
            started=time.monotonic()
            worker,errors=self.start(self.power.climate_delay_tick)
            worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(errors),1)
            self.assertLess(time.monotonic()-started,3.5)
            self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
