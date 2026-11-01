import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
import backup_restore as restore
from backup_export import export_snapshot, secrets_manifest, stage_snapshot
from backup_export_manifest import git_paths
from backup_protocol import seal
from backup_service import BackupService
from restore_archive import prepare_database, snapshot, secrets
from restore_smoke import smoke
import restore_runtime


class RestoreContractTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.target=self.root/'target';self.target.mkdir()
        self.targets={name:self.target/name for name in ('scripts','infra','apps')}
        self.stage=self.root/'staging';self.locks=self.root/'locks'

    def archive(self, rows, name='fixture.tar.gz'):
        path=self.root/name
        with tarfile.open(path,'w:gz') as tar:
            for rel,kind,value,mode in rows:
                info=tarfile.TarInfo('backup/'+rel);info.mode=mode;info.mtime=1600000000
                if kind=='file':info.size=len(value);tar.addfile(info,io.BytesIO(value))
                else:
                    info.type={'dir':tarfile.DIRTYPE,'symlink':tarfile.SYMTYPE,'hardlink':tarfile.LNKTYPE,'fifo':tarfile.FIFOTYPE}[kind]
                    if kind in ('symlink','hardlink'):info.linkname=value
                    tar.addfile(info)
        return path

    def apply(self, archive, selections, mode='in_place'):
        return restore.restore(archive,selections,mode,'RESTORE',self.targets,self.stage,self.locks)

    def test_late_database_rejection_leaves_prior_file_unchanged(self):
        path=self.targets['scripts']/'existing.sh';path.parent.mkdir();path.write_bytes(b'before')
        archive=self.archive([('scripts/existing.sh','file',b'after',0o750),('postgres/db.dump','file',b'dump',0o600)])
        with self.assertRaises(ValueError):self.apply(archive,['scripts','postgres'])
        self.assertEqual(path.read_bytes(),b'before');self.assertFalse(list(self.stage.iterdir()))

    def test_entire_selection_validated_before_write(self):
        archive=self.archive([('scripts/first','file',b'after',0o600),('unknown/late','file',b'bad',0o600)])
        with self.assertRaises(ValueError):self.apply(archive,['scripts','unknown'])
        self.assertFalse(self.targets['scripts'].exists())

    def test_archive_path_attacks_and_duplicates(self):
        for path in ('scripts/../../escape','/absolute','scripts/..','scripts/a\\b'):
            with self.subTest(path=path):
                archive=self.archive([(path,'file',b'bad',0o600)])
                with self.assertRaises(ValueError):self.apply(archive,['scripts'])
        archive=self.archive([('scripts/a','file',b'a',0o600),('scripts/a','file',b'b',0o600)])
        with self.assertRaises(ValueError):self.apply(archive,['scripts'])

    def test_compare_rejects_traversal_and_symlink_before_read(self):
        service=BackupService(lambda *a:None,lambda *a:None);service.restore_targets=self.targets
        service.read_member_text=lambda *a: self.fail('Archive/current read happened before target validation')
        for path in ('scripts/../../outside','/scripts/a'):
            with self.assertRaises(ValueError):service.compare_file('unused',path)
        self.targets['scripts'].mkdir();(self.targets['scripts']/'escape').symlink_to(self.root)
        with self.assertRaises(ValueError):service.compare_file('unused','scripts/escape/secret')

    def test_symlink_destination_and_special_member_fail_before_write(self):
        self.targets['scripts'].symlink_to(self.root)
        archive=self.archive([('scripts/x','file',b'after',0o600)])
        with self.assertRaises(ValueError):self.apply(archive,['scripts'])
        self.targets['scripts'].unlink()
        archive=self.archive([('scripts/x','file',b'after',0o600),('scripts/fifo','fifo','',0o600)])
        with self.assertRaises(ValueError):self.apply(archive,['scripts'])
        self.assertFalse(self.targets['scripts'].exists())

    def test_metadata_empty_directory_and_executable_survive(self):
        archive=self.archive([('scripts/run.sh','file',b'#!/bin/sh\nexit 0\n',0o4750),('scripts/private','file',b'private',0o600),('scripts/empty','dir','',0o710)])
        result=self.apply(archive,['scripts']);self.assertTrue(result['ok'])
        for name,mode in [('run.sh',0o750),('private',0o600),('empty',0o710)]:
            info=(self.targets['scripts']/name).stat();self.assertEqual(stat.S_IMODE(info.st_mode),mode);self.assertEqual(int(info.st_mtime),1600000000)
        subprocess.run([str(self.targets['scripts']/'run.sh')],check=True)

    def test_supported_links_and_explicit_target_selection(self):
        archive=self.archive([('scripts/a','file',b'content',0o640),('scripts/b','hardlink','backup/scripts/a',0o640),('scripts/link','symlink','a',0o777)])
        result=self.apply(archive,['scripts']);self.assertTrue(result['ok'])
        self.assertEqual((self.targets['scripts']/'a').stat().st_ino,(self.targets['scripts']/'b').stat().st_ino)
        self.assertEqual(os.readlink(self.targets['scripts']/'link'),'a')
        recovered=restore.recover(result['run_id'],self.stage,self.targets,self.locks,'ROLLBACK')
        self.assertTrue(recovered['ok']);self.assertFalse((self.targets['scripts']/'link').exists())
        with self.assertRaises(ValueError):self.apply(archive,['scripts/b'])

    def test_escaping_links_fail_preflight(self):
        for link in ('../outside','/etc/passwd'):
            with self.subTest(link=link):
                archive=self.archive([('scripts/link','symlink',link,0o777)])
                with self.assertRaises(ValueError):self.apply(archive,['scripts'])

    def test_disk_full_reports_partial_and_recovers_content_and_mode(self):
        path=self.targets['scripts']/'a';path.parent.mkdir();path.write_bytes(b'before');path.chmod(0o600);os.utime(path,(1500000000,1500000000))
        archive=self.archive([('scripts/a','file',b'after',0o750),('scripts/b','file',b'new',0o600)])
        install=restore._install
        def fail_second(row,*args):
            if row['path']=='scripts/b':raise OSError(errno.ENOSPC,'synthetic disk full')
            return install(row,*args)
        with patch.object(restore,'_install',side_effect=fail_second):result=self.apply(archive,['scripts'])
        self.assertFalse(result['ok']);self.assertTrue(result['recovery_required']);self.assertEqual(len(result['restored']),1)
        self.assertEqual(path.read_bytes(),b'after')
        recovered=restore.recover(result['run_id'],self.stage,self.targets,self.locks,'ROLLBACK')
        self.assertTrue(recovered['ok']);self.assertEqual(path.read_bytes(),b'before');self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600);self.assertEqual(int(path.stat().st_mtime),1500000000)
        self.assertTrue(restore.recover(result['run_id'],self.stage,self.targets,self.locks,'ROLLBACK')['ok'])

    def test_invalid_mode_empty_missing_or_db_choice_never_creates_target(self):
        archive=self.archive([('scripts/a','file',b'a',0o600)])
        for choices,mode in [([], 'staging'),(['missing'],'staging'),(['scripts'],'typo')]:
            with self.assertRaises(ValueError):self.apply(archive,choices,mode)
        self.assertFalse(self.targets['scripts'].exists())

    def test_staging_is_unique_for_repeated_archive(self):
        archive=self.archive([('postgres/db.dump','file',b'a',0o600)])
        a=self.apply(archive,['postgres'],'staging');b=self.apply(archive,['postgres'],'staging')
        self.assertNotEqual(a['target'],b['target']);self.assertEqual((Path(a['target'])/'postgres/db.dump').read_bytes(),b'a')

    def test_shared_lock_blocks_restore(self):
        archive=self.archive([('scripts/a','file',b'a',0o600)])
        with restore.restore_lock(self.locks):
            with self.assertRaisesRegex(ValueError,'busy'):self.apply(archive,['scripts'])

    def test_process_exit_after_replace_remains_discoverable_and_recoverable(self):
        path=self.targets['scripts']/'a';path.parent.mkdir();path.write_bytes(b'before')
        archive=self.archive([('scripts/a','file',b'after',0o750),('scripts/new/sub/b','file',b'new',0o600)])
        code='''import backup_restore as r,json,os,sys
from pathlib import Path
a=json.loads(sys.argv[1]);original=r._install
def die(*args):
 original(*args)
 if args[0]['path'].endswith('/b'): os._exit(97)
r._install=die
r.restore(a['archive'],['scripts'],'in_place','RESTORE',a['targets'],a['stage'],a['locks'])
'''
        args=json.dumps(dict(archive=str(archive),targets={k:str(v) for k,v in self.targets.items()},stage=str(self.stage),locks=str(self.locks)))
        result=subprocess.run([sys.executable,'-c',code,args],env={**os.environ,'PYTHONPATH':str(Path(restore.__file__).parent)})
        self.assertEqual(result.returncode,97);self.assertEqual(path.read_bytes(),b'after')
        pending=restore.recoveries(self.stage);self.assertEqual(len(pending),1);self.assertTrue(pending[0]['recovery_required'])
        self.assertTrue(restore.recover(pending[0]['run_id'],self.stage,self.targets,self.locks,'ROLLBACK')['ok'])
        self.assertEqual(path.read_bytes(),b'before');self.assertFalse((self.targets['scripts']/'new').exists())

    def test_recovery_refuses_later_operator_edit(self):
        archive=self.archive([('scripts/a','file',b'after',0o750)])
        result=self.apply(archive,['scripts']);(self.targets['scripts']/'a').write_text('operator edit')
        with self.assertRaisesRegex(ValueError,'changed since restore'):
            restore.recover(result['run_id'],self.stage,self.targets,self.locks,'ROLLBACK')
        self.assertEqual((self.targets['scripts']/'a').read_text(),'operator edit')

    def verified_archive(self,name,db=b'db'):
        source=self.root/('source-'+name);source.mkdir()
        (source/'scripts').mkdir();(source/'scripts/run.sh').write_text('code')
        if db is not None:(source/'postgres').mkdir();(source/'postgres/db.dump').write_bytes(db)
        seal(source,'local',{'postgres':db is not None})
        archive=self.root/(name+'.tar.gz')
        with tarfile.open(archive,'w:gz') as tar:tar.add(source,arcname=name)
        return archive

    def test_new_then_old_archive_selection_never_uses_stale_dump(self):
        new=self.verified_archive('new',b'NEW');old=self.verified_archive('old',b'OLD');empty=self.verified_archive('none',None)
        work=self.root/'reused'
        a=prepare_database(new,work);b=prepare_database(old,work)
        self.assertNotEqual(a['dump'],b['dump']);self.assertEqual(Path(b['dump']).read_bytes(),b'OLD')
        with self.assertRaises(ValueError):prepare_database(empty,work)
        self.assertEqual(Path(a['dump']).read_bytes(),b'NEW')

    def test_corrupt_archive_checksum_rejected(self):
        archive=self.verified_archive('corrupt')
        with tarfile.open(archive) as tar: members=[(m,tar.extractfile(m).read() if m.isfile() else None) for m in tar.getmembers()]
        with tarfile.open(archive,'w:gz') as tar:
            for m,data in members:
                if m.name.endswith('db.dump'):data=b'XX';m.size=len(data)
                tar.addfile(m,io.BytesIO(data) if data is not None else None)
        with self.assertRaises(ValueError):prepare_database(archive,self.root/'work')

    def test_snapshot_selection_ignores_newer_other_tag_and_pins_id(self):
        rows=[{'id':'a'*64,'time':'2026-01-01','tags':['homecontrol']},{'id':'b'*64,'time':'2026-02-01','tags':['other']}]
        self.assertEqual(snapshot(rows),'a'*64)
        with self.assertRaises(ValueError):snapshot(rows,'bbbb')
        with self.assertRaises(ValueError):snapshot([])

    def test_secret_archive_traversal_and_links_are_rejected_without_writes(self):
        archive=self.archive([('SECRETS_BUNDLE_CONTENTS.txt','file',b'list',0o600),('../escape','file',b'bad',0o600)])
        with self.assertRaises(ValueError):secrets(archive,self.root/'secret-stage')
        self.assertFalse((self.root/'secret-stage').exists())

    def test_custom_target_full_launchers_stop_before_commands(self):
        scripts=Path(__file__).resolve().parents[3]/'scripts'
        for name,args in [('bootstrap_restore_v0_1.sh',['--apply','--skip-restic']),('homecontrol_restore_magic.sh',['--full','--confirm-new-hc-server'])]:
            result=subprocess.run(['bash',str(scripts/name),'--target',str(self.root/'custom')]+args,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('only supports /srv/docker/homecontrol',result.stderr)
            self.assertFalse((self.root/'custom').exists())

    def test_smoke_empty_restic_result_is_failure_and_uses_pinned_id(self):
        archive=self.verified_archive('smoke');self.locks.mkdir()
        password=self.root/'password';password.write_text('synthetic')
        (self.locks/'backup_settings.json').write_text(json.dumps({'git_enabled':False,'restic_enabled':True,'restic_password_file':str(password)}))
        calls=[]
        def fake(args,**kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args,0,json.dumps([{'id':'a'*64,'time':'2026','tags':['homecontrol']}]),'')
        # This is the legacy SFTP transport's empty-restore contract, independent
        # of the installed deployment policy (which currently disables AI SFTP).
        with patch.dict(os.environ,{'BACKUP_ROOT':str(self.locks)}), patch('restore_smoke.effective_backup_settings',side_effect=lambda settings:settings):
            with self.assertRaises(ValueError):smoke(self.root,archive,run=fake)
        self.assertIn('a'*64,calls[-1]);self.assertNotIn('latest',calls[-1]);self.assertFalse(json.loads((self.locks/'restore-smoke-result.json').read_text())['ok'])


class ExportContractTest(unittest.TestCase):
    def test_nested_gitignore_cannot_hide_manifest_source_and_runtime_maps_are_excluded(self):
        self.write('apps/tool/.gitignore', '*.sql\n')
        self.write('apps/tool/schema.sql', 'select 1;')
        self.write('apps/xiaomi-x10/x10_maps/map_object_fixture.json', '{}')
        self.write('apps/xiaomi-x10/x10_maps/floor.png', 'runtime-map')
        self.write('apps/xiaomi-x10/x10_maps/xiaomi_cloud_auth.json', '{"ssecurity":"synthetic"}')
        subprocess.run(['git', 'init', '-q', str(self.out)], check=True)
        export_snapshot(self.base, self.out)
        staged = stage_snapshot(self.out)
        paths = set(subprocess.check_output(['git', '-C', str(self.out), 'ls-files', '-z']).decode().rstrip('\0').split('\0'))
        manifest = json.loads((self.out/'EXPORT_MANIFEST.json').read_text())
        self.assertEqual(paths, {row['path'] for row in manifest['files']} | {'.gitignore', 'EXPORT_MANIFEST.json'})
        self.assertIn('apps/tool/schema.sql', paths)
        self.assertFalse(any('/x10_maps/' in name for name in paths))
        self.assertEqual(staged['staged_files'], len(paths))

    def test_changed_export_is_rejected_before_git_staging(self):
        self.write('scripts/tool.py', 'source')
        subprocess.run(['git', 'init', '-q', str(self.out)], check=True)
        export_snapshot(self.base, self.out)
        (self.out/'scripts/tool.py').write_text('tampered')
        with self.assertRaises(ValueError):
            stage_snapshot(self.out)
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.out), 'ls-files']), b'')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base=self.root/'project';self.base.mkdir();self.out=self.root/'export'
    def write(self,name,value='source'):
        path=self.base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value);return path
    def test_fresh_and_existing_tracked_auth_variants_excluded(self):
        for suffix in ('.json','.json.bak','.json.old','.backup'):
            self.write('apps/xiaomi-x10/x10_maps/xiaomi_cloud_auth'+suffix,'{"ssecurity":"synthetic"}')
        self.write('apps/xiaomi-x10/app.py');self.out.mkdir();(self.out/'.git').mkdir();(self.out/'already-tracked-secret').write_text('old')
        result=export_snapshot(self.base,self.out)
        self.assertFalse((self.out/'already-tracked-secret').exists());self.assertTrue((self.out/'.git').is_dir())
        self.assertFalse(list(self.out.rglob('xiaomi_cloud_auth*')));self.assertTrue((self.out/'apps/xiaomi-x10/app.py').exists())
    def test_complete_reviewed_inventory_and_private_files(self):
        for name in ('infra/db/001.sql','infra/proxy/default.conf','infra/mqtt/config/mosquitto.conf','infra/mdns/Dockerfile','scripts/safe.sh'):
            self.write(name)
        self.write('homeassistant/config/secrets.yaml','synthetic');self.write('infra/.env','secret');self.write('infra/ssh/ai_node_key','secret');self.write('secrets/private.txt','secret');self.write('secrets/bundle.age','encrypted')
        export_snapshot(self.base,self.out)
        for name in ('db/001.sql','proxy/default.conf','mqtt/config/mosquitto.conf','mdns/Dockerfile'):self.assertTrue((self.out/'infra'/name).exists())
        self.assertFalse((self.out/'homeassistant/config/secrets.yaml').exists());self.assertFalse((self.out/'infra/.env').exists());self.assertFalse((self.out/'infra/ssh').exists());self.assertFalse((self.out/'secrets/private.txt').exists())
        self.assertTrue((self.out/'secrets/bundle.age').exists());self.assertEqual(json.loads((self.out/'EXPORT_MANIFEST.json').read_text())['sources'],git_paths())
    def test_unknown_credential_file_fails_without_destroying_checkout(self):
        self.write('apps/tool/unexpected.json','{"serviceToken":"synthetic-secret"}')
        self.out.mkdir();(self.out/'.git').mkdir();(self.out/'keep').write_text('before')
        with self.assertRaises(ValueError):export_snapshot(self.base,self.out)
        self.assertEqual((self.out/'keep').read_text(),'before')
    def test_auth_variants_added_to_private_encrypted_manifest_only(self):
        self.write('secrets/manifest.txt','infra/.env\n');auth=self.write('apps/xiaomi-x10/x10_maps/xiaomi_cloud_auth.json.bak','synthetic')
        output=self.root/'private-manifest';secrets_manifest(self.base,output)
        self.assertIn(str(auth),output.read_text());self.assertEqual(stat.S_IMODE(output.stat().st_mode),0o600)
        self.assertEqual((self.base/'secrets/manifest.txt').read_text(),'infra/.env\n')
    def test_runtime_env_preparation_is_idempotent_and_private(self):
        env=self.write('infra/.env','POSTGRES_USER=homecontrol\nPOSTGRES_DB=homecontrol\nPOSTGRES_PASSWORD="synthetic admin"\n')
        a=restore_runtime.environment(self.base);b=restore_runtime.environment(self.base)
        self.assertEqual(a,b);self.assertEqual(stat.S_IMODE(env.stat().st_mode),0o600);self.assertNotEqual(a['HC_APP_DB_PASSWORD'],a['HC_LAB_DB_PASSWORD'])


if __name__=='__main__':unittest.main()
