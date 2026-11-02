import contextlib
import io
import json
from pathlib import Path
import socket
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from scripts.refresh_x10_cloud_auth import (CONTAINER_INSTALL, LoginError,
    LoginImagePreview, capture_login, refresh, validated_session)


class CloudLoginTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'xiaomi_cloud_auth.json'
        self.path.write_text(json.dumps(dict(country='de', userId='account',
                                            ssecurity='previous', serviceToken='previous')))
        self.original = self.path.read_bytes()
        self.connector = SimpleNamespace(userId='account', _ssecurity='new-security',
            _serviceToken='new-session', login=lambda: True,
            get_dev_cnt=lambda country: {'code': 0},
            _session=SimpleNamespace(request=lambda *a, **kw: None))
        fake_config = SimpleNamespace(XIAOMI_CLOUD_AUTH=self.path, XIAOMI_CLOUD_COUNTRY='de')
        self.namespace = {'__name__': 'login_test'}
        with patch.dict('sys.modules', config=fake_config):
            exec(compile(CONTAINER_INSTALL, '<install-payload>', 'exec'), self.namespace)

    def login(self):
        auth = validated_session(self.connector, 'de')
        with contextlib.redirect_stdout(io.StringIO()), patch('sys.stdin', io.StringIO(json.dumps(auth))):
            self.namespace['install']()

    def test_expired_new_session_cannot_replace_existing_file(self):
        self.connector.get_dev_cnt = lambda country: None
        with self.assertRaises(LoginError):
            self.login()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_different_account_cannot_replace_existing_file(self):
        self.connector.userId = 'another-account'
        with self.assertRaises(self.namespace['SessionInstallError']):
            self.login()
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_verified_session_replaces_and_keeps_private_previous_copy(self):
        self.login()
        self.assertEqual(json.loads(self.path.read_text())['serviceToken'], 'new-session')
        previous = list(self.path.parent.glob(self.path.name + '.previous.*'))
        self.assertEqual(len(previous), 1)
        self.assertEqual(previous[0].read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(previous[0].stat().st_mode), 0o600)

    def test_failed_replace_retains_previous_auth_and_removes_temporary(self):
        with patch('os.replace', side_effect=OSError('simulated replacement failure')):
            with self.assertRaises(OSError):
                self.login()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(list(self.path.parent.glob('.x10-auth-*')))
        self.assertEqual(len(list(self.path.parent.glob(self.path.name + '.previous.*'))), 1)

    def test_incomplete_session_is_not_installed(self):
        self.connector._serviceToken = None
        with self.assertRaises(LoginError):
            self.login()
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_wrong_region_is_not_installed(self):
        auth = validated_session(self.connector, 'us')
        with patch('sys.stdin', io.StringIO(json.dumps(auth))):
            with self.assertRaises(self.namespace['SessionInstallError']):
                self.namespace['install']()
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_failed_native_login_does_not_validate_or_install(self):
        self.connector.get_dev_cnt = lambda country: self.fail('Must not validate failed login')
        with self.assertRaises(LoginError):
            capture_login(lambda connector: False, 'de')(self.connector)

    def test_native_password_and_qr_selection_save_without_listing_device_tokens(self):
        for method in ('p', 'q'):
            with self.subTest(method=method):
                source = '''
class PasswordXiaomiCloudConnector:
    userId = 'account'
    _ssecurity = 'fixture-security'
    _serviceToken = 'fixture-session'
    def login(self): return True
    def get_dev_cnt(self, country): return {'code': 0}
class QrCodeXiaomiCloudConnector(PasswordXiaomiCloudConnector):
    def login(self): return True
def main():
    connector = PasswordXiaomiCloudConnector() if METHOD == 'p' else QrCodeXiaomiCloudConnector()
    connector.login()
    raise AssertionError('Device token listing must not run')
'''
                path = Path(self.folder.name) / 'extractor.py'
                path.write_text('METHOD = ' + repr(method) + '\n' + source)
                completed = SimpleNamespace(returncode=0, stdout='de\n')
                with patch('subprocess.run', return_value=completed) as run:
                    self.assertEqual(refresh(path), 0)
                self.assertEqual(run.call_count, 2)
                install = run.call_args
                self.assertEqual(install.args[0][:3], ['docker', 'exec', '-i'])
                self.assertEqual(json.loads(install.kwargs['input'])['serviceToken'], 'fixture-session')
                self.assertNotIn('fixture-session', repr(install.args[0]))


class LoginImagePreviewTest(unittest.TestCase):
    def setUp(self):
        self.preview = LoginImagePreview(port=0)
        self.addCleanup(self.preview.close)

    def show(self, data):
        with contextlib.redirect_stdout(io.StringIO()):
            self.preview.show(data)
        return self.preview.server.server_address

    def test_browser_receives_latest_image_and_listener_is_loopback_only(self):
        host, port = self.show(b'\x89PNG\r\n\x1a\nfixture-one')
        self.assertEqual(host, '127.0.0.1')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
            self.assertEqual(response.read(), b'\x89PNG\r\n\x1a\nfixture-one')
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.show(b'\xff\xd8\xfffixture-two')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/image?v=2', timeout=2) as response:
            self.assertEqual(response.read(), b'\xff\xd8\xfffixture-two')
            self.assertEqual(response.headers['Content-Type'], 'image/jpeg')
        self.preview.close()
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', port), timeout=1)

    def test_image_server_does_not_serve_file_paths(self):
        host, port = self.show(b'GIF89afixture')
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f'http://{host}:{port}/etc/passwd', timeout=2)
        self.assertEqual(error.exception.code, 404)

    def test_busy_port_reports_failure_without_using_other_process_image(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            other = LoginImagePreview(port=occupied.getsockname()[1])
            with self.assertRaises(LoginError):
                other.show(b'GIF89afixture')
            self.assertIsNone(other.server)
            other.close()

    def test_native_extractor_uses_preview_and_cleans_up_when_login_fails(self):
        source = '''
def present_image_image(*args, **kwargs):
    raise AssertionError('Original image display should be replaced')
class PasswordXiaomiCloudConnector:
    def login(self):
        present_image_image(b'GIF89afixture', message_url='unused')
        return False
class QrCodeXiaomiCloudConnector(PasswordXiaomiCloudConnector): pass
def main(): PasswordXiaomiCloudConnector().login()
'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'extractor.py'
            path.write_text(source)
            result = SimpleNamespace(returncode=0, stdout='de\n')
            with patch('subprocess.run', return_value=result), \
                    patch('scripts.refresh_x10_cloud_auth.LoginImagePreview') as preview:
                with self.assertRaises(LoginError):
                    refresh(path)
                preview.return_value.show.assert_called_once_with(b'GIF89afixture', message_url='unused')
                preview.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
