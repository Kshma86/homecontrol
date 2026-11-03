import io
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from flask import Flask

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backup_restore
from backup_service import BackupService
from api_route_modules import register_backup_routes


class RestoreHttpTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.service=BackupService(lambda *a:None,lambda *a:None)
        self.service.backup_root=root/'backups';self.service.backup_root.mkdir()
        self.service.restore_staging_root=root/'stage';self.service.restore_targets={'scripts':root/'scripts'}
        self.existing=root/'scripts/a';self.existing.parent.mkdir();self.existing.write_text('before')
        self.archive='homecontrol_http_fixture.tar.gz'
        with tarfile.open(self.service.backup_root/self.archive,'w:gz') as tar:
            for name in ('a','b'):
                row=tarfile.TarInfo('backup/scripts/'+name);row.size=5;row.mode=0o750
                tar.addfile(row,io.BytesIO(b'after'))
        app=Flask(__name__)
        register_backup_routes(app,get_context_service=lambda:SimpleNamespace(section=lambda name:self.service.payload()),
            get_backup_service=lambda:self.service,invalidate_context_sections=lambda *a:None,
            context_command_meta=lambda *a:{},json_ready=lambda value:value)
        self.client=app.test_client()

    def test_partial_http_409_contains_recovery_and_rollback_restores_preimage(self):
        original=backup_restore._install
        def fail(row,*args):
            if row['path']=='scripts/b':raise PermissionError('synthetic destination permission failure')
            return original(row,*args)
        with patch.object(backup_restore,'_install',side_effect=fail):
            response=self.client.post('/api/backup/restore',json=dict(backup=self.archive,paths=['scripts'],mode='in_place',confirm='RESTORE'))
        body=response.get_json()
        self.assertEqual(response.status_code,409);self.assertFalse(body['ok']);self.assertTrue(body['recovery_required'])
        self.assertEqual(len(body['restored']),1);self.assertEqual(body['remaining'],['scripts/b'])
        response=self.client.post('/api/backup/restore/recover',json=dict(run_id=body['run_id'],confirm='ROLLBACK'))
        self.assertEqual(response.status_code,200);self.assertTrue(response.get_json()['ok']);self.assertEqual(self.existing.read_text(),'before')

    def test_late_unsupported_selection_returns_400_without_destination_change(self):
        response=self.client.post('/api/backup/restore',json=dict(backup=self.archive,paths=['scripts','missing'],mode='in_place',confirm='RESTORE'))
        self.assertEqual(response.status_code,400);self.assertFalse(response.get_json()['ok']);self.assertEqual(self.existing.read_text(),'before')


if __name__=='__main__':unittest.main()
