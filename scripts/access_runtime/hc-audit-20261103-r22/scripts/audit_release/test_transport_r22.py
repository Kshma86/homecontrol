import importlib.util
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('router_transport_r22', root / 'infra/backend/router_backup.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


class TransportTests(unittest.TestCase):
    def repo(self): return r.RouterRepository({**r.DEFAULTS, 'backup_target': 'router_ftp',
                                             'restic_password_file': '/fixture/restic-password'})

    def test_pool_is_drained_before_the_socket_deadline(self):
        repo = self.repo()
        options = shlex.split(next(arg for arg in repo.command if arg.startswith('rclone.args=')).split('=', 1)[1])
        self.assertEqual(options[options.index('--ftp-idle-timeout') + 1], '10s')
        self.assertEqual(options[options.index('--timeout') + 1], '30s')

    def test_serialization_and_bounded_retries_are_preserved(self):
        repo = self.repo()
        args = next(arg for arg in repo.command if arg.startswith('rclone.args='))
        for option in ('--checkers 1', '--transfers 1', '--retries 1', '--low-level-retries 1', '--contimeout 10s'):
            self.assertIn(option, args)
        self.assertIn('rclone.connections=2', repo.command)
        self.assertNotIn('--no-check-upload', args)
        self.assertNotIn('--no-check-certificate', args)

    def test_ambient_remote_and_password_overrides_stay_blocked(self):
        with patch.dict(r.os.environ, {'RCLONE_CONFIG': '/untrusted', 'RESTIC_PASSWORD': 'untrusted'}):
            repo = self.repo()
        self.assertEqual(repo.env['RCLONE_CONFIG'], r.DEFAULTS['router_rclone_config'])
        self.assertNotIn('RESTIC_PASSWORD', repo.env)


if __name__ == '__main__': unittest.main(verbosity=2)
