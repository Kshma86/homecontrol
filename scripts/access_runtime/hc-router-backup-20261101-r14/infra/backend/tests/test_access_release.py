import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/access_release'))
from common import cancel_intent, no_symlinks, restore_snapshot, snapshot, units
from network import execute, rules
import backup_assets
import prepare as access_prepare
import restore_assets
from backup_protocol import seal
from common import digest
spec=importlib.util.spec_from_file_location('access_install',ROOT/'scripts/access_release/install.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
from scoped_ai_power_coordination import ScopedAiPowerCoordinator


class AccessReleaseTest(unittest.TestCase):
    def recovery_fixture(self, root):
        payload=root/'payload';prefix=payload/'scripts/access_runtime'/backup_assets.NAME
        images=prefix/'images';images.mkdir(parents=True)
        image=images/'access-images.tar.gz';image.write_bytes(b'disposable-offline-image')
        postgres='sha256:'+'1'*64
        (images/'manifest.json').write_text(json.dumps({'archive':image.name,'sha256':digest(image),'images':[postgres]}))
        (prefix/'runtime.compose.json').write_text(json.dumps({'services':{'postgres':{'image':postgres}}}))
        (payload/'infra').mkdir();(payload/'infra/access-release.json').write_text(json.dumps({'release':backup_assets.NAME,'image_archive_sha256':digest(image)}))
        jobs=payload/'infra/ssh'/backup_assets.NAME/'host-jobs';jobs.mkdir(parents=True)
        (jobs/('a'*32+'.json')).write_text('{"state":"uncertain"}')
        (payload/'backups').mkdir();(payload/'backups/backup_settings.json').write_text('{"schedule_time":"04:27"}')
        seal(payload,'local',{})
        archive=root/'fixture.tar.gz'
        with tarfile.open(archive,'w:gz') as out:out.add(payload,arcname='fixture')
        return archive,payload

    def test_recovery_assets_stage_is_verified_bounded_and_does_not_start_docker(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive,payload=self.recovery_fixture(root)
            with patch('restore_assets.subprocess.run',side_effect=AssertionError('stage must be read only')):
                manifest=restore_assets.stage_assets(archive,root/'stage',base=root/'blank-host')
            staged,value=restore_assets.checked_stage(manifest)
            self.assertFalse(value['previous_owned']);self.assertEqual(len(value['files']),4)
            self.assertEqual(value['postgres_image'],'sha256:'+'1'*64)
            target=root/'restored-runtime';private=root/'restored-private'
            with patch.object(restore_assets,'RUNTIME',target),patch.object(restore_assets,'PRIVATE',private),patch.object(restore_assets,'BASE',root/'host'):restore_assets.apply_assets(manifest)
            self.assertTrue((target/'images/access-images.tar.gz').is_file())
            self.assertTrue((private/'host-jobs'/('a'*32+'.json')).is_file())
            self.assertEqual(json.loads((root/'host/backups/backup_settings.json').read_text())['schedule_time'],'04:27')
            (staged/'images/access-images.tar.gz').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):restore_assets.checked_stage(manifest)

    def test_corrupt_selected_archive_is_rejected_before_recovery_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive,payload=self.recovery_fixture(root)
            (payload/'scripts/access_runtime'/backup_assets.NAME/'images/access-images.tar.gz').write_bytes(b'tampered')
            with tarfile.open(archive,'w:gz') as out:out.add(payload,arcname='fixture')
            with self.assertRaises(ValueError):restore_assets.stage_assets(archive,root/'stage',base=root/'blank-host')
            self.assertFalse((root/'stage').exists())

    def test_backup_preserves_offline_images_and_marks_unfinished_jobs_uncertain(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);private=root/'private';images=private/'images';images.mkdir(parents=True)
            image=images/'cache.tar.gz';image.write_bytes(b'offline fixture')
            (images/'manifest.json').write_text(json.dumps({'archive':image.name,'sha256':digest(image)}))
            journal=root/'jobs';journal.mkdir()
            settings=root/'settings.json';settings.write_text('{"schedule_time":"04:27"}')
            (journal/'pending.json').write_text(json.dumps({'state':'running','id':'fixture'}))
            archive=root/'archive'
            with patch.dict(os.environ,{'HC_ACCESS_PRIVATE':str(private)}),patch.object(backup_assets,'JOURNAL',journal),patch.object(backup_assets,'SETTINGS',settings):
                backup_assets.collect(archive)
                self.assertEqual((archive/'scripts/access_runtime'/backup_assets.NAME/'images'/image.name).read_bytes(),image.read_bytes())
                receipt=json.loads((archive/'infra/ssh'/backup_assets.NAME/'host-jobs/pending.json').read_text())
                self.assertEqual(receipt['state'],'uncertain')
                self.assertEqual(json.loads((journal/'pending.json').read_text())['state'],'running')
                self.assertEqual((archive/'backups/backup_settings.json').read_bytes(),settings.read_bytes())
                image.write_bytes(b'corrupted')
                with self.assertRaises(ValueError):backup_assets.collect(root/'bad-archive')
                self.assertFalse((root/'bad-archive').exists())

    def test_repeated_journal_restore_is_idempotent_but_cannot_replace_newer_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);incoming=root/'incoming';incoming.mkdir()
            (incoming/'job.json').write_text('{"state":"uncertain"}')
            target=root/'target';installer.restore_jobs(incoming,target);installer.restore_jobs(incoming,target)
            (target/'job.json').write_text('{"state":"completed"}')
            with self.assertRaises(ValueError):installer.restore_jobs(incoming,target)
            self.assertEqual(json.loads((target/'job.json').read_text())['state'],'completed')

    def test_pending_esp_approval_cannot_deploy(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'approval.json';path.write_text(json.dumps({'esp_ip':'192.168.1.179','esp_identity_confirmed':False,'fixed_ip_confirmed':False}))
            with self.assertRaises(ValueError):installer.approval(path)
            path.write_text(json.dumps({'esp_ip':'192.168.1.179','esp_identity_confirmed':True,'fixed_ip_confirmed':True}))
            self.assertEqual(installer.approval(path)['esp_ip'],'192.168.1.179')

    def test_unconfirmed_esp_cannot_finalize_or_mutate_the_package(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'approval.json';path.write_text(json.dumps({'esp_ip':'192.168.1.179','esp_identity_confirmed':False,'fixed_ip_confirmed':False}))
            with self.assertRaises(ValueError):access_prepare.confirm_esp(root/'kit',path)
            self.assertFalse((root/'kit').exists())

    def test_state_handover_cancels_old_intent_without_mutating_original(self):
        state={'version':1,'generation':'old','intent':{'action':'power_off'},'backup':{'active':False}}
        value=cancel_intent(state,'handover')
        self.assertIsNone(value['intent']);self.assertNotEqual(value['generation'],'old')
        self.assertIsNotNone(state['intent'])
        state['backup']['active']=True
        with self.assertRaises(ValueError):cancel_intent(state,'handover')

    def test_exact_file_and_symlink_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);file=root/'config';file.write_text('previous');file.chmod(0o640)
            link=root/'override';link.symlink_to('previous-release.json');missing=root/'new-unit'
            snapshot([file,link,missing],root/'snapshot')
            file.write_text('new');link.unlink();link.write_text('new');missing.write_text('unit')
            restore_snapshot(root/'snapshot')
            self.assertEqual(file.read_text(),'previous');self.assertEqual(file.stat().st_mode & 0o777,0o640)
            self.assertEqual(os.readlink(link),'previous-release.json');self.assertFalse(missing.exists())

    def test_protected_parent_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'redirect';path.symlink_to('/tmp')
            with self.assertRaises(ValueError):no_symlinks(path/'state')

    def test_firewall_is_atomic_owned_and_has_no_global_flush(self):
        policy=dict(esp_ip='192.168.1.179',broker_ip='172.19.0.9',docker_subnet='172.19.0.0/16',dashboard_ip='192.168.1.89',mode='authenticated',owned_chain=False)
        calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs));return subprocess.CompletedProcess(args,1 if args[:3]==['nft','list','table'] else 0,'','')
        execute(policy,run)
        batch=calls[-1][1]['input']
        self.assertIn('hook forward',batch);self.assertIn('hook output',batch);self.assertIn('nfproto ipv6',batch)
        self.assertNotIn('flush ruleset',batch);self.assertNotIn('192.168.1.89',batch)
        policy['mode']='rollback';self.assertIn('172.19.0.0/16',rules(policy))
        self.assertIn('192.168.1.89',rules(policy))

    def test_existing_unowned_firewall_table_cannot_be_replaced(self):
        run=lambda args,**kwargs:subprocess.CompletedProcess(args,0,'','')
        with self.assertRaises(RuntimeError):execute(dict(esp_ip='192.168.1.179',broker_ip='172.19.0.9',mode='authenticated',owned_chain=False),run)

    def test_rendered_units_preserve_f6_and_do_not_remove_firewall_on_stop(self):
        values=units(ROOT)
        self.assertEqual(len([n for n in values if n.endswith('/hc44.conf')]),5)
        self.assertNotIn('ExecStop=',values['homecontrol-mqtt-access.service'])
        self.assertIn('access_runtime/hc-router-backup-20261101-r14',values['homecontrol-hostops.service'])
        self.assertIn('restore_host.py',values['homecontrol-backup-apply.service.d/hc-access.conf'])
        self.assertIn('ExecStartPre=',values['docker.service.d/hc-access.conf'])
        self.assertIn('homecontrol-post-boot-health.timer',values)

    def test_boot_network_pins_all_existing_endpoints_and_rejects_unknown_peer(self):
        rows={name:{'Name':'/hc-'+name,'NetworkSettings':{'Networks':{'hc_net':{'IPAddress':address}}}}
              for name,address in (('mqtt','172.19.0.9'),('backend','172.19.0.8'))}
        network={'Name':'hc_net','IPAM':{'Config':[{'Subnet':'172.19.0.0/16'}]},
                 'Containers':{name:{'Name':'hc-'+name,'IPv4Address':row['NetworkSettings']['Networks']['hc_net']['IPAddress']+'/16'} for name,row in rows.items()}}
        model={'services':{'mqtt':{},'backend':{}}}
        expected=access_prepare.pin_network_addresses(model,rows,network)
        self.assertEqual(expected,{'hc-mqtt':'172.19.0.9','hc-backend':'172.19.0.8'})
        self.assertEqual(model['services']['backend']['networks']['default']['ipv4_address'],'172.19.0.8')
        network['Containers']['unknown']={'Name':'foreign','IPv4Address':'172.19.0.7/16'}
        with self.assertRaises(ValueError):access_prepare.pin_network_addresses(model,rows,network)

    def test_full_restore_reconciles_fan_intents_before_starting_host_services(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'binding-release.json').write_text('{}')
            events=[]
            with patch.object(installer,'RUNTIME',root),patch.object(installer,'PRIVATE',root),\
                 patch('climate_handover.reconcile',side_effect=lambda *a:events.append('reconciled')),\
                 patch.object(installer,'call',side_effect=lambda *a:events.append('started')):
                installer.start_runtime()
            self.assertEqual(events,['reconciled','started'])

    def test_full_restore_fan_handover_failure_prevents_host_service_start(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'binding-release.json').write_text('{}')
            with patch.object(installer,'RUNTIME',root),patch.object(installer,'PRIVATE',root),\
                 patch('climate_handover.reconcile',side_effect=RuntimeError('database unavailable')),\
                 patch.object(installer,'call') as start:
                with self.assertRaises(RuntimeError):installer.start_runtime()
                start.assert_not_called()

    def test_symlink_fifo_and_hardlinked_state_lock_cannot_change_host_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);coordinator=ScopedAiPowerCoordinator(root)
            coordinator.state_root.mkdir();victim=root/'victim';victim.write_text('protected');uid=victim.stat().st_uid
            lock=coordinator.state_root/'ai-power-coordination.lock'
            for kind in ('symlink','fifo','hardlink'):
                if kind=='symlink':lock.symlink_to(victim)
                elif kind=='fifo':os.mkfifo(lock)
                else:os.link(victim,lock)
                with self.subTest(kind=kind), self.assertRaises((ValueError,OSError)):
                    with coordinator.locked():pass
                self.assertEqual(victim.read_text(),'protected');self.assertEqual(victim.stat().st_uid,uid)
                lock.unlink()

    def test_scoped_state_read_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);coordinator=ScopedAiPowerCoordinator(root);coordinator.state_root.mkdir()
            secret=root/'private';secret.write_text('{"version":1,"secret":"hidden"}')
            coordinator.path.symlink_to(secret)
            with self.assertRaises(OSError):coordinator.read()

    def test_root_writer_leaves_state_and_lock_accessible_to_nonroot_api(self):
        self.assertEqual(os.geteuid(),0,'Run this ownership test in the isolated root test container')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);root.chmod(0o755)
            coordinator=ScopedAiPowerCoordinator(root);coordinator.state_root.mkdir();os.chown(coordinator.state_root,10001,10001)
            coordinator.begin_backup('fixture');coordinator.finish_backup('fixture')
            self.assertEqual(coordinator.path.stat().st_uid,10001)
            self.assertEqual((coordinator.state_root/'ai-power-coordination.lock').stat().st_uid,10001)
            code='from pathlib import Path;from scoped_ai_power_coordination import ScopedAiPowerCoordinator;import sys;c=ScopedAiPowerCoordinator(Path(sys.argv[1]));\nwith c.locked() as s: assert s["backup"]["active"] is False;c.save(s)'
            def demote():os.setgid(10001);os.setuid(10001)
            subprocess.run([sys.executable,'-c',code,str(root)],check=True,preexec_fn=demote,capture_output=True)


if __name__=='__main__':unittest.main()
