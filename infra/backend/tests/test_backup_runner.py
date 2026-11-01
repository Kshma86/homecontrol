"""F6 real process/lock/archive tests on synthetic roots and fake external commands."""
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

from backup_protocol import (atomic_json,enqueue,inventory,jobs,lock_state,read_json,retention,seal,sha256,tail,verify_archive)
from backup_service import BackupService

PROJECT=Path(__file__).resolve().parents[3]
RUNNER=PROJECT/'scripts/backup_runner.py'

FAKE = r'''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['F6_TRACE'],'a') as f:f.write(json.dumps([name]+args)+'\n')
if name=='docker' and 'pg_dump' in args:
 if os.environ.get('F6_BLOCK_DUMP'):time.sleep(60)
 if os.environ.get('F6_FAIL_DUMP'):sys.exit(41)
 sys.stdout.buffer.write(b'SYNTHETIC-PG-DUMP');sys.exit(0)
if name=='tar':
 if '-czf' in args and os.environ.get('F6_BLOCK_TAR'):
  Path(args[args.index('-czf')+1]).write_bytes(b'incomplete');time.sleep(60)
 if '-czf' in args and os.environ.get('F6_FAIL_TAR'):
  Path(args[args.index('-czf')+1]).write_bytes(b'incomplete');sys.exit(28)
 os.execv('/bin/tar',['/bin/tar']+args)
if name=='git':
 if 'diff' in args:sys.exit(1)
 if 'push' in args and 'origin' in args and os.environ.get('F6_FAIL_ORIGIN'):sys.exit(128)
 if 'push' in args and 'offsite' in args and os.environ.get('F6_FAIL_OFFSITE'):sys.exit(128)
if name=='ssh' and any('backup_gitea.sh' in a for a in args) and os.environ.get('F6_FAIL_GITEA_DUMP'):sys.exit(1)
if name=='ssh' and args[-1:] == ['true'] and os.environ.get('F6_FIRST_SSH_OFFLINE'):
 rows=[json.loads(line) for line in Path(os.environ['F6_TRACE']).read_text().splitlines()]
 if sum(row[0]=='ssh' and row[-1:] == ['true'] for row in rows)==1:sys.exit(255)
if name=='ssh' and os.environ.get('F6_OFFLINE'):sys.exit(255)
if name=='restic' and 'backup' in args and os.environ.get('F6_FAIL_RESTIC'):sys.exit(1)
if name=='restic' and 'forget' in args and os.environ.get('F6_FAIL_RETENTION'):sys.exit(1)
if name=='restic' and 'check' in args and os.environ.get('F6_FAIL_CHECK'):sys.exit(1)
print('{}')
'''


class BackupRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)/'project';self.root=Path(self.temp.name)/'backups';self.root.mkdir()
        for name in ['apps','infra','infra/zigbee2mqtt/data','scripts','homeassistant','media']:
            path=self.base/name;path.mkdir(parents=True,exist_ok=True);(path/'fixture.txt').write_text(name)
        (self.base/'scripts/create_secrets_bundle.sh').write_text('#!/bin/sh\n[ -z "$F6_FAIL_SECRETS" ]\n')
        (self.base/'scripts/export_gitea_config_snapshot.sh').write_text('#!/bin/sh\nmkdir -p "$1"\nprintf fixture > "$1/config.txt"\n')
        (self.base/'scripts/export_config_snapshot.py').write_text("import pathlib,sys\nif '--secrets-manifest' in sys.argv: pathlib.Path(sys.argv[-1]).write_text('synthetic')\nelse:\n p=pathlib.Path(sys.argv[1]);p.mkdir(exist_ok=True,parents=True);(p/'config.txt').write_text('fixture')\n")
        for p in (self.base/'scripts').glob('*.sh'):p.chmod(0o700)
        bin=Path(self.temp.name)/'bin';bin.mkdir();fake=bin/'fake';fake.write_text(FAKE);fake.chmod(0o700)
        for command in ['docker','ssh','git','restic','tar']:(bin/command).symlink_to(fake)
        password=Path(self.temp.name)/'restic-password';password.write_text('synthetic')
        self.settings={**BackupService.DEFAULT_SETTINGS,'restic_enabled':True,'restic_password_file':str(password),
                       'git_offsite_enabled':True,'git_offsite_remote':'synthetic-offsite','ai_weekly_shutdown_after':False}
        self.trace=Path(self.temp.name)/'trace.jsonl'
        self.env={**os.environ,'PATH':str(bin)+':'+os.environ['PATH'],'F6_TRACE':str(self.trace),
                  'HC_PROJECT_ROOT':str(self.base),'BACKUP_ROOT':str(self.root),'TMPDIR':self.temp.name,
                  'HC_BACKUP_VOLUMES_ROOT':str(self.base/'volumes'),'HC_BACKUP_GITEA_ROOT':str(self.base/'gitea'),
                  'AI_BACKUP_SHUTDOWN_AFTER':'false','AI_BACKUP_WAIT_SECONDS':'0','AI_CHECK_WAKE':'false'}
        assets=Path(self.temp.name)/'access-private/images';assets.mkdir(parents=True)
        (assets/'fixture.tar.gz').write_bytes(b'synthetic-image-cache')
        atomic_json(assets/'manifest.json',dict(archive='fixture.tar.gz',sha256=sha256(assets/'fixture.tar.gz')))
        self.env['HC_ACCESS_PRIVATE']=str(assets.parent)
        self.save_settings()

    def save_settings(self):atomic_json(self.root/'backup_settings.json',self.settings)

    def run_job(self,mode='weekly',**flags):
        result=subprocess.run([sys.executable,str(RUNNER),'--root',str(self.root),'--mode',mode],env={**self.env,**flags},capture_output=True,text=True,timeout=30)
        if result.returncode not in (0,1,75):self.fail(result.stderr)
        return result

    def commands(self):return [json.loads(x) for x in self.trace.read_text().splitlines()]

    def service(self):
        with patch.dict(os.environ,{'HC_BACKUP_DIR':str(self.root)}):
            return BackupService(lambda *a:self.fail('No Docker calls from web'),lambda *a:self.fail('No dump from web'))

    def assert_mandatory_attempted(self):
        commands=self.commands()
        self.assertTrue(any(c[0]=='docker' and 'pg_dump' in c for c in commands))
        self.assertTrue(any(c[0]=='restic' and 'backup' in c for c in commands))
        self.assertTrue(any(c[0]=='ssh' and any('backup_gitea.sh' in a for a in c) for c in commands))
        self.assertTrue(any(c[0]=='git' and 'push' in c and 'offsite' in c for c in commands))

    def test_weekly_success_has_independent_targets_and_verified_archive(self):
        result=self.run_job();self.assertEqual(result.returncode,0,result.stderr)
        self.assert_mandatory_attempted()
        state=read_json(self.root/'backup-state.json');self.assertEqual(state['state'],'completed')
        for target in ['local_archive','gitea_origin','git_offsite','gitea_dump','restic','restic_retention']:
            self.assertEqual(state['targets'][target]['state'],'succeeded')
        row=inventory(self.root)[0];self.assertTrue(row['completed'])
        self.assertGreater(verify_archive(row['path'])['verified_files'],5)
        with tarfile.open(row['path']) as archive:
            names=archive.getnames();self.assertTrue(any('/zigbee2mqtt/data/fixture.txt' in n for n in names))
            self.assertTrue(any('/postgres/' in n and n.endswith('.dump') for n in names))

    def test_origin_failure_still_attempts_offsite_local_and_restic(self):
        self.assertEqual(self.run_job(F6_FAIL_ORIGIN='1').returncode,1)
        self.assert_mandatory_attempted()
        state=read_json(self.root/'backup-state.json');self.assertEqual(state['targets']['git_offsite']['state'],'succeeded')
        self.assertEqual(state['state'],'failed');self.assertTrue(self.service().latest_info()['ok'])

    def test_offsite_failure_cannot_be_reported_as_success(self):
        self.assertEqual(self.run_job(F6_FAIL_OFFSITE='1').returncode,1)
        self.assert_mandatory_attempted();self.assertEqual(read_json(self.root/'backup-state.json')['targets']['gitea_origin']['state'],'succeeded')

    def test_gitea_dump_failure_does_not_skip_mandatory_restic(self):
        self.assertEqual(self.run_job(F6_FAIL_GITEA_DUMP='1').returncode,1);self.assert_mandatory_attempted()

    def test_restic_failure_retains_prior_success_and_local_archive(self):
        self.assertEqual(self.run_job().returncode,0)
        old=read_json(self.root/'backup-targets.json')['restic']['last_success']
        self.assertEqual(self.run_job(F6_FAIL_RESTIC='1').returncode,1)
        target=read_json(self.root/'backup-targets.json')['restic']
        self.assertEqual(target['last_success'],old);self.assertEqual(target['last_attempt']['state'],'failed')
        self.assertEqual(len(inventory(self.root)),2)
        self.assertIn('restic',self.service().activity()['latest_error'])
        # A local-only success must not erase a failed remote destination.
        self.settings['restic_enabled']=False;self.save_settings()
        self.assertEqual(self.run_job('local').returncode,0)
        self.assertEqual(read_json(self.root/'backup-targets.json')['restic']['last_attempt']['state'],'failed')
        self.assertIn('restic',self.service().activity()['latest_error'])

    def test_required_weekly_restic_is_attempted_even_when_daily_restic_disabled(self):
        self.settings['restic_enabled']=False;self.save_settings()
        self.assertEqual(self.run_job().returncode,0);self.assert_mandatory_attempted()

    def test_optional_secrets_failure_does_not_skip_backup_or_hide_target_failure(self):
        self.assertEqual(self.run_job(F6_FAIL_SECRETS='1').returncode,0)
        self.assert_mandatory_attempted()
        self.assertEqual(read_json(self.root/'backup-targets.json')['secrets_bundle']['last_attempt']['state'],'failed')

    def test_dump_failure_and_tar_disk_full_publish_nothing_and_keep_old_archives(self):
        self.assertEqual(self.run_job('local').returncode,0)
        old=inventory(self.root)[0]['name']
        for flags in ({'F6_FAIL_DUMP':'1'},{'F6_FAIL_TAR':'1'}):
            with self.subTest(flags=flags):
                self.assertEqual(self.run_job('local',**flags).returncode,1)
                self.assertEqual([r['name'] for r in inventory(self.root)],[old])
                self.assertFalse(list(self.root.glob('*.partial')))

    def test_ui_only_queues_and_never_reports_creation(self):
        service=self.service();payload,status=service.create_payload(lambda *a:{})
        self.assertEqual(status,202);self.assertNotIn('backup',payload)
        self.assertEqual(payload['request']['state'],'queued')
        self.assertFalse(service.latest_info()['ok']);self.assertFalse(self.trace.exists())
        result=subprocess.run([sys.executable,str(RUNNER),'--root',str(self.root),'--drain'],env=self.env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(jobs(self.root)[0]['state'],'completed');self.assertTrue(service.latest_info()['ok'])
        self.assertFalse(list((self.root/'requests').glob('*')))

    def test_invalid_host_request_is_quarantined_without_execution(self):
        request=enqueue(self.root,'local');path=self.root/'requests'/(request['run_id']+'.json')
        atomic_json(path,{**request,'command':'forbidden'})
        result=subprocess.run([sys.executable,str(RUNNER),'--root',str(self.root),'--drain'],env=self.env,capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertFalse(self.trace.exists())
        self.assertFalse(list((self.root/'requests').glob('*')));self.assertTrue(list((self.root/'rejected').glob('*')))

    def start_blocked(self,stage="dump"):
        proc=subprocess.Popen([sys.executable,str(RUNNER),'--root',str(self.root),'--mode','local'],env={**self.env,'F6_BLOCK_'+stage.upper():'1'},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        self.addCleanup(lambda:proc.kill() if proc.poll() is None else None)
        self.addCleanup(proc.stderr.close)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.trace.exists() and any(('pg_dump' if stage=='dump' else '-czf') in row for row in self.commands()):return proc
            if proc.poll() is not None:self.fail(proc.stderr.read())
            time.sleep(.02)
        self.fail('dump did not start')

    def test_web_and_timer_share_lock_and_term_records_failure(self):
        proc=self.start_blocked()
        request=enqueue(self.root,'local')
        self.assertEqual(self.run_job('local').returncode,75)
        self.assertTrue(lock_state(self.root/'homecontrol-backup.lock'))
        proc.terminate();proc.wait(timeout=10)
        self.assertEqual(proc.returncode,1)
        self.assertFalse(lock_state(self.root/'homecontrol-backup.lock'));self.assertFalse(inventory(self.root))
        self.assertEqual(read_json(self.root/'backup-state.json')['state'],'failed')
        self.assertTrue((self.root/'requests'/(request['run_id']+'.json')).exists())

    def test_termination_during_tar_cannot_publish_a_complete_archive(self):
        proc=self.start_blocked("tar")
        self.assertTrue(list(self.root.glob('*.partial')))
        proc.terminate();proc.wait(timeout=10)
        self.assertEqual(proc.returncode,1);self.assertFalse(inventory(self.root))
        self.assertFalse(list(self.root.glob('*.partial')))

    def test_permission_failure_cannot_remove_last_verified_archive(self):
        self.assertEqual(self.run_job('local').returncode,0)
        name=inventory(self.root)[0]['name'];self.root.chmod(0o500)
        try:self.assertEqual(self.run_job('local').returncode,1)
        finally:self.root.chmod(0o700)
        self.assertTrue((self.root/name).exists());self.assertEqual(inventory(self.root)[0]['name'],name)

    def test_restic_retention_failure_and_check_failure_are_distinct(self):
        self.assertEqual(self.run_job(F6_FAIL_RETENTION='1').returncode,1)
        history=read_json(self.root/'backup-targets.json')
        self.assertEqual(history['restic']['last_attempt']['state'],'succeeded')
        self.assertEqual(history['restic_retention']['last_attempt']['state'],'failed')
        self.assertEqual(self.run_job('check',F6_FAIL_CHECK='1').returncode,1)
        self.assertEqual(read_json(self.root/'backup-targets.json')['restic']['last_success'],history['restic']['last_success'])

    def test_killed_parent_cannot_release_lock_while_worker_is_still_active(self):
        proc=self.start_blocked()
        children=Path(f'/proc/{proc.pid}/task/{proc.pid}/children').read_text().split()
        self.assertTrue(children);worker=int(children[0])
        try:
            proc.kill();proc.wait(timeout=5)
            self.assertTrue(lock_state(self.root/'homecontrol-backup.lock'))
            self.assertEqual(self.run_job('local').returncode,75)
        finally:
            try:os.killpg(worker,signal.SIGKILL)
            except ProcessLookupError:pass
        deadline=time.monotonic()+5
        while lock_state(self.root/'homecontrol-backup.lock') and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(lock_state(self.root/'homecontrol-backup.lock'))
        self.assertEqual(jobs(self.root)[0]['state'],'interrupted')
        self.assertFalse(inventory(self.root))

    def test_completion_shutdown_has_run_id_and_is_after_restic_even_when_git_fails(self):
        self.assertEqual(self.run_job(F6_FAIL_ORIGIN='1',F6_FIRST_SSH_OFFLINE='1',AI_BACKUP_SHUTDOWN_AFTER='true').returncode,1)
        commands=self.commands();backup=next(i for i,c in enumerate(commands) if c[0]=='restic' and 'backup' in c)
        shutdown=next(i for i,c in enumerate(commands) if '/api/ai/node/command' in c)
        self.assertGreater(shutdown,backup)
        body=json.loads(commands[shutdown][-1])
        state=read_json(self.root/'backup-state.json')
        self.assertEqual(body['backup_run_id'],state['run_id'])
        self.assertNotIn('defer_if_backup_running',body)

    def test_new_job_invalidates_old_power_intent_and_keeps_finished_run_identity(self):
        from ai_power_coordination import AiPowerCoordinator
        power=AiPowerCoordinator(self.root)
        with power.locked() as state:
            power.invalidate(state,'fixture intent')
            old=state['generation'];state['intent']={'generation':old,'phase':'off'};power.save(state)
        self.assertEqual(self.run_job('local').returncode,0)
        state=power.read();self.assertIsNone(state['intent']);self.assertNotEqual(state['generation'],old)
        self.assertFalse(state['backup']['active'])
        self.assertEqual(state['backup']['run_id'],read_json(self.root/'backup-state.json')['run_id'])

    def test_restic_check_wake_and_completion_use_the_same_run_id(self):
        result=self.run_job('check',F6_FIRST_SSH_OFFLINE='1',AI_CHECK_WAKE='true',AI_CHECK_WAIT_SECONDS='0')
        self.assertEqual(result.returncode,0,result.stderr)
        commands=self.commands()
        wake=next(c for c in commands if '/api/ai/node/wake' in c)
        shutdown=next(c for c in commands if '/api/ai/node/command' in c)
        run_id=read_json(self.root/'backup-state.json')['run_id']
        self.assertEqual(json.loads(wake[-1])['backup_run_id'],run_id)
        self.assertEqual(json.loads(shutdown[-1])['backup_run_id'],run_id)
        check=next(i for i,c in enumerate(commands) if c[0]=='restic' and 'check' in c)
        self.assertGreater(commands.index(shutdown),check)

    def test_unknown_power_coordination_state_blocks_job_before_external_work(self):
        (self.root/'ai-power-state.json').write_text('invalid state')
        self.assertEqual(self.run_job('local').returncode,1)
        self.assertFalse(self.trace.exists());self.assertFalse(inventory(self.root))

    def test_retention_only_removes_verified_old_archive_after_verified_success(self):
        self.assertEqual(self.run_job('local').returncode,0)
        row=inventory(self.root)[0];path=Path(row['path']);old=time.time()-30*86400;os.utime(path,(old,old))
        receipt=path.with_name(path.name+'.complete.json');data=read_json(receipt);data['mtime_ns']=path.stat().st_mtime_ns;atomic_json(receipt,data)
        legacy=self.root/'homecontrol_2000-01-01_00-00-00.tar.gz';legacy.write_bytes(b'old-unverified');os.utime(legacy,(old,old))
        self.assertEqual(self.run_job('local',F6_FAIL_TAR='1').returncode,1);self.assertTrue(path.exists())
        self.assertEqual(self.run_job('local').returncode,0);self.assertFalse(path.exists());self.assertTrue(legacy.exists())

    def test_settings_lock_checksum_partial_and_uncommitted_final_are_not_success(self):
        for name in ['backup_settings.json','homecontrol-backup.lock','full-ai-backup.request','orphan.tar.gz.partial']:
            (self.root/name).touch()
        orphan=self.root/('homecontrol_2026-01-01_00-00-00_'+'a'*32+'.tar.gz');orphan.write_bytes(b'incomplete')
        self.assertFalse(self.service().latest_info()['ok']);self.assertFalse(inventory(self.root))
        with self.assertRaisesRegex(ValueError,'committed'):self.service().safe_path(orphan.name)

    def test_checksum_corruption_is_rejected_without_extracting_any_file(self):
        directory=Path(self.temp.name)/'data';directory.mkdir();(directory/'a').write_text('correct');seal(directory,'local',{})
        (directory/'a').write_text('changed')
        archive=Path(self.temp.name)/'corrupt.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:tar.add(directory,arcname='homecontrol_fixture')
        with self.assertRaisesRegex(ValueError,'checksum'):verify_archive(archive)

    def test_nested_manifest_names_survive_runner_and_restore(self):
        expected={f'{directory}/{name}':f'original {directory}/{name}\n'.encode()
                  for directory in ('scripts','homeassistant')
                  for name in ('MANIFEST.txt','SHA256SUMS.txt')}
        for name,data in expected.items():(self.base/name).write_bytes(data)
        self.assertEqual(self.run_job('local').returncode,0)
        row=inventory(self.root)[0];self.assertTrue(row['completed'])
        verify_archive(row['path'])
        with tarfile.open(row['path']) as archive:
            prefix=archive.getnames()[0].split('/')[0]
            for name,data in expected.items():
                with self.subTest(name=name):
                    self.assertEqual(archive.extractfile(prefix+'/'+name).read(),data)

    def test_nested_manifest_corruption_is_rejected(self):
        for name in ('MANIFEST.txt','SHA256SUMS.txt'):
            with self.subTest(name=name):
                directory=Path(self.temp.name)/name;directory.mkdir()
                (directory/'nested').mkdir();source=directory/'nested'/name
                source.write_text('original');seal(directory,'local',{})
                source.write_text('corrupted')
                path=Path(self.temp.name)/(name+'.tar.gz')
                with tarfile.open(path,'w:gz') as archive:archive.add(directory,arcname='fixture')
                with self.assertRaisesRegex(ValueError,'checksum'):verify_archive(path)

    def test_hardlinks_survive_runner_and_restore(self):
        source=self.base/'scripts/link-a.txt';source.write_bytes(b'shared hardlink payload\n')
        os.link(source,self.base/'scripts/link-b.txt')
        self.assertEqual(self.run_job('local').returncode,0)
        row=inventory(self.root)[0];self.assertTrue(row['completed'])
        verify_archive(row['path'])
        with tarfile.open(row['path']) as archive:
            members={m.name.rsplit('/',1)[-1]:m for m in archive if m.name.endswith(('link-a.txt','link-b.txt'))}
            self.assertEqual(len(members),2)
            self.assertEqual(sum(m.islnk() for m in members.values()),1)
            for member in members.values():
                self.assertEqual(archive.extractfile(member).read(),source.read_bytes())

    def test_hardlink_target_content_must_match_its_checksum(self):
        import hashlib
        data={'a':b'original','c':b'other content'}
        sums=''.join(hashlib.sha256(value).hexdigest()+'  ./'+name+'\n' for name,value in data.items())
        sums+=hashlib.sha256(data['a']).hexdigest()+'  ./b\n'
        path=Path(self.temp.name)/'wrong-link.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            for name,value in {**data,'SHA256SUMS.txt':sums.encode()}.items():
                member=tarfile.TarInfo('fixture/'+name);member.size=len(value);archive.addfile(member,io.BytesIO(value))
            link=tarfile.TarInfo('fixture/b');link.type=tarfile.LNKTYPE;link.linkname='fixture/c';archive.addfile(link)
        with self.assertRaisesRegex(ValueError,'checksum'):verify_archive(path)

    def test_hardlinks_to_missing_or_foreign_members_are_rejected(self):
        import hashlib
        data=b'original';checksum=hashlib.sha256(data).hexdigest()
        for target in ('fixture/missing','other/a','fixture/b'):
            with self.subTest(target=target):
                path=Path(self.temp.name)/'bad-link.tar.gz'
                with tarfile.open(path,'w:gz') as archive:
                    for name,value in {'a':data,'SHA256SUMS.txt':(checksum+'  ./a\n'+checksum+'  ./b\n').encode()}.items():
                        member=tarfile.TarInfo('fixture/'+name);member.size=len(value);archive.addfile(member,io.BytesIO(value))
                    link=tarfile.TarInfo('fixture/b');link.type=tarfile.LNKTYPE;link.linkname=target;archive.addfile(link)
                with self.assertRaisesRegex(ValueError,'hardlink'):verify_archive(path)

    def test_bounded_log_reads_and_lock_probe_have_no_filesystem_writes(self):
        missing=self.root/'missing'/'lock';self.assertFalse(lock_state(missing));self.assertFalse(missing.parent.exists())
        log=self.root/'backup.log'
        with log.open('wb') as stream:stream.seek(64*1024*1024);stream.write(b'\n[2026-10-23 12:00:00] last marker\n')
        with patch.object(Path,'read_text',side_effect=AssertionError('Unbounded text read')):
            self.assertIn('last marker',tail(log,10)[-1])
            self.assertIsNotNone(self.service().latest_log_timestamp('last marker'))
        log.rename(log.with_suffix('.rotated'));log.write_text('new log\n');self.assertEqual(tail(log),['new log'])
        with patch.object(Path,'open',side_effect=PermissionError):self.assertIsNone(lock_state(missing))

    def test_partial_selection_is_explicit_and_identical_for_ui_and_timer(self):
        self.settings.update(include_postgres=False,include_apps=False,restic_enabled=False);self.save_settings()
        self.assertEqual(self.run_job('local').returncode,0)
        row=inventory(self.root)[0];self.assertFalse(row['coverage']['include_postgres']);self.assertFalse(row['coverage']['include_apps'])
        request=enqueue(self.root,'local')
        result=subprocess.run([sys.executable,str(RUNNER),'--root',str(self.root),'--drain'],env=self.env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        rows=inventory(self.root);self.assertEqual(rows[0]['coverage'],rows[1]['coverage']);self.assertNotEqual(rows[0]['name'],rows[1]['name'])


if __name__=='__main__':unittest.main()
