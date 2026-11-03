"""Real local Git/age staging under restrictive caller permissions."""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[2]


class BootstrapCheckoutTest(unittest.TestCase):
    def test_umask_077_keeps_work_and_secrets_private_but_checkout_readable_on_repeat(self):
        with tempfile.TemporaryDirectory(prefix='hc-bootstrap-permissions-') as folder:
            root = Path(folder)
            repo = root / 'repo'
            (repo / 'scripts').mkdir(parents=True)
            (repo / 'infra/backend').mkdir(parents=True)
            (repo / 'infra/db').mkdir()
            (repo / 'infra/db/source.sql').write_text('select 1;\n')
            executable = repo / 'scripts/source.sh'
            executable.write_text('#!/bin/sh\nexit 0\n'); executable.chmod(0o755)
            shutil.copyfile(BASE / 'scripts/restore_archive.py', repo / 'scripts/restore_archive.py')
            for name in ('backup_protocol.py', 'backup_restore.py'):
                shutil.copyfile(BASE / 'infra/backend' / name, repo / 'infra/backend' / name)
            identity = root / 'identity'
            subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
            recipient = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
            plain = root / 'plain'; (plain / 'srv/docker/homecontrol/infra').mkdir(parents=True)
            (plain / 'SECRETS_BUNDLE_CONTENTS.txt').write_text('fixture\n')
            (plain / 'srv/docker/homecontrol/infra/.env').write_text('FIXTURE=private\n')
            archive = root / 'private.tar.gz'
            with tarfile.open(archive, 'w:gz') as out: out.add(plain, arcname='.')
            (repo / 'secrets').mkdir()
            bundle = repo / 'secrets/homecontrol-secrets-latest.tar.gz.age'
            subprocess.run(['age', '-r', recipient, '-o', str(bundle), str(archive)], check=True, capture_output=True)
            bundle.with_name(bundle.name + '.sha256').write_text(hashlib.sha256(bundle.read_bytes()).hexdigest() + '\n')
            subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
            subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(repo), '-c', 'user.name=HC test', '-c', 'user.email=test@localhost',
                            'commit', '-qm', 'Disposable bootstrap fixture'], check=True)
            work = root / 'work'
            script = BASE / 'scripts/bootstrap_restore_v0_1.sh'
            for _ in range(2):
                subprocess.run(['bash', str(script), '--age-key', str(identity), '--repo-url', str(repo),
                                '--repo-ref', 'main', '--work-dir', str(work), '--skip-restic'],
                               check=True, capture_output=True, preexec_fn=lambda: os.umask(0o077))
                self.assertEqual(stat.S_IMODE(work.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((work / 'project/infra/db').stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE((work / 'project/infra/db/source.sql').stat().st_mode), 0o644)
                self.assertEqual(stat.S_IMODE((work / 'project/scripts/source.sh').stat().st_mode), 0o755)
                private = list((work / 'secrets').glob('rootfs.*/srv/docker/homecontrol/infra/.env'))
                self.assertTrue(private)
                self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in private))


if __name__ == '__main__':
    unittest.main()
