"""Full-platform SQL availability and fail-closed rollback ordering."""
import importlib.util,json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import platform_transaction as transaction
import activate


class PlatformTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.events=[]
        self.manifest={'changed_services':['backend','postgres','mqtt','hc_ingest'],
            'baseline':{'homecontrol-postgres':{'image':'sha256:'+'1'*64}}}
        class Cutover:
            def stop(self):raise AssertionError('Old app-only stop must be replaced')
        self.core=SimpleNamespace(BASE=self.base,KIT=self.base,phase=lambda _:None,
            Cutover=Cutover,container=lambda s:'homecontrol-'+s,
            call=lambda args,**kw:self.events.append(args),
            reconcile=lambda reason:self.events.append('sql-'+reason),
            compose=lambda path:['docker','compose','-f',str(path)])
        transaction.install_hooks(self.core,self.manifest)

    def test_stop_keeps_postgres_alive_until_sql_handover(self):
        self.core.Cutover().stop()
        self.assertEqual(self.events[0][-1],'homecontrol-backend')
        self.assertTrue(all('homecontrol-postgres' not in args for args in self.events))
        self.assertIn('homecontrol-mqtt',self.events[1])

    def test_deploy_sql_commits_before_database_stop(self):
        self.core.reconcile('deploy')
        self.assertEqual(self.events[0],'sql-deploy')
        self.assertEqual(self.events[1][-1],'homecontrol-postgres')

    def test_failed_sql_does_not_stop_database(self):
        core=SimpleNamespace(**vars(self.core));core.Cutover=type('Cutover',(),{})
        core.reconcile=Mock(side_effect=RuntimeError('handover failed'));core.call=Mock()
        transaction.install_hooks(core,self.manifest)
        with self.assertRaises(RuntimeError):core.reconcile('deploy')
        core.call.assert_not_called()

    def test_rollback_starts_previous_database_before_sql(self):
        with patch.object(transaction,'restore_database_owner',side_effect=lambda *a:self.events.append('old-database-ready')):
            self.core.reconcile('rollback')
        self.assertEqual(self.events,['old-database-ready','sql-rollback'])

    def test_failed_old_database_recovery_blocks_sql_and_continuation(self):
        with patch.object(transaction,'restore_database_owner',side_effect=RuntimeError('not ready')):
            with self.assertRaises(RuntimeError):self.core.reconcile('rollback')
        self.assertEqual(self.events,[])

    def test_database_recovery_uses_previous_image_and_waits_for_real_query(self):
        writes=[]
        results=[SimpleNamespace(returncode=0,stdout=b''),SimpleNamespace(returncode=1,stdout=b''),SimpleNamespace(returncode=0,stdout=b'1\n')]
        self.core.call=Mock(side_effect=results)
        self.core.platform=lambda:SimpleNamespace(write_json=lambda p,v:writes.append(v))
        with patch.object(transaction.time,'sleep'):transaction.restore_database_owner(self.core,self.manifest)
        self.assertEqual(writes[0]['services']['postgres']['image'],self.manifest['baseline']['homecontrol-postgres']['image'])
        self.assertEqual(self.core.call.call_count,3)
        args=self.core.call.call_args_list[0].args[0]
        self.assertEqual(args[-1],'postgres');self.assertIn('--no-deps',args)
        self.assertIn('SELECT 1',self.core.call.call_args.args[0][-1])

    def production_core(self):
        spec=importlib.util.spec_from_file_location('platform_core_fixture',activate.SOURCE/'scripts/f10_release/deploy.py')
        core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
        core.BASE=self.base;core.KIT=self.base;core.STATE=self.base/'transition'
        self.db_running=True;self.backend_running=True
        def command(args,**kwargs):
            self.events.append(args)
            if args[:2]==['docker','stop']:
                if 'homecontrol-postgres' in args:self.db_running=False
                if 'homecontrol-backend' in args:self.backend_running=False
            if 'up' in args and 'postgres' in args:
                self.db_running=True
                if 'backend' in args:self.backend_running=True
            return SimpleNamespace(returncode=0,stdout=b'1\n')
        def sql(reason):
            self.assertTrue(self.db_running,'Real transaction attempted SQL after PostgreSQL stop')
            self.assertFalse(self.backend_running,'Old backend must stop before SQL handover')
            self.events.append('sql-'+reason)
        def write(path,value,*args):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
        core.call=command;core.reconcile=sql;core.phase=lambda _:None
        core.locked=lambda _:None;core.idle=lambda:None;core.active=lambda _:False
        core.platform=lambda:SimpleNamespace(write_json=write,restore_snapshot=lambda _:self.events.append('restore-files'))
        transaction.install_hooks(core,self.manifest)
        return core

    def test_actual_deployer_stop_install_order_keeps_sql_available(self):
        core=self.production_core();core.install_files=lambda _:self.events.append('install-files')
        context=core.Cutover(self.manifest,{})
        context.stop();self.assertTrue(self.db_running)
        context.install();self.assertFalse(self.db_running)
        self.assertLess(self.events.index('sql-deploy'),self.events.index('install-files'))

    def test_actual_deployer_rollback_recovers_database_before_handover(self):
        core=self.production_core()
        (self.base/'infra').mkdir();(self.base/'infra/access-release.json').write_text(json.dumps({'release':core.NAME}))
        core.STATE.mkdir();(core.STATE/'transition.json').write_text(json.dumps({'release':core.NAME,'active_timers':{}}))
        core.wait_ready=lambda *args,**kwargs:self.assertTrue(self.db_running and self.backend_running)
        core.rollback(self.manifest)
        self.assertIn('sql-rollback',self.events)
        self.assertLess(self.events.index('sql-rollback'),self.events.index('restore-files'))


if __name__=='__main__':unittest.main()
