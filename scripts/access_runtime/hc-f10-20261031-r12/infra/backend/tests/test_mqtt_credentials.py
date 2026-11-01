import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from mqtt_credentials import configure_mqtt_auth

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('hc41_prepare', ROOT/'scripts/prepare_mqtt_access.py')
prepare_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_module)


class MqttCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True);self.env.start();self.addCleanup(self.env.stop)
        self.client = Mock()

    def test_existing_unconfigured_deployment_remains_compatible(self):
        self.assertFalse(configure_mqtt_auth(self.client))
        self.client.username_pw_set.assert_not_called()

    def test_required_missing_credentials_fail_closed(self):
        os.environ['MQTT_AUTH_REQUIRED'] = '1'
        with self.assertRaises(ValueError):configure_mqtt_auth(self.client)
        self.client.username_pw_set.assert_not_called()

    def test_file_and_x10_generic_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'secret';p.write_text('test-password\n')
            os.environ.update(MQTT_USERNAME='hc_x10', MQTT_PASSWORD_FILE=str(p))
            self.assertTrue(configure_mqtt_auth(self.client, prefix='X10_MQTT'))
            self.client.username_pw_set.assert_called_once_with('hc_x10', 'test-password')

    def test_partial_explicit_x10_does_not_use_another_identity(self):
        os.environ.update(X10_MQTT_USERNAME='hc_x10', MQTT_USERNAME='other', MQTT_PASSWORD='other-secret')
        with self.assertRaises(ValueError):configure_mqtt_auth(self.client, prefix='X10_MQTT')

    def test_invalid_explicit_credentials_do_not_fall_back_to_tuya_config(self):
        os.environ['MQTT_USERNAME'] = 'hc_tuya'
        with self.assertRaises(ValueError):configure_mqtt_auth(self.client, fallback=('old', 'old-secret'))

    def test_existing_tuya_configuration_is_supported(self):
        self.assertTrue(configure_mqtt_auth(self.client, fallback=('old', 'old-secret')))
        self.client.username_pw_set.assert_called_once_with('old', 'old-secret')

    def test_conflicting_secrets_are_rejected(self):
        os.environ.update(MQTT_USERNAME='a', MQTT_PASSWORD='b', MQTT_PASSWORD_FILE='/missing')
        with self.assertRaises(ValueError):configure_mqtt_auth(self.client)

    def test_unreadable_oversized_and_multiline_secrets_are_not_exposed(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'secret'
            os.environ.update(MQTT_USERNAME='a', MQTT_PASSWORD_FILE=str(p))
            for value in (None, 'private-marker\nsecond', 'x'*4096+'\nmore'):
                if value is not None:p.write_text(value)
                with self.subTest(value_length=len(value or '')), self.assertRaises(ValueError) as caught:
                    configure_mqtt_auth(self.client)
                self.assertNotIn('private-marker', str(caught.exception))
            self.client.username_pw_set.assert_not_called()

    def test_all_independent_image_contexts_have_the_same_helper(self):
        source = (ROOT/'infra/backend/mqtt_credentials.py').read_bytes()
        for folder in ('hc_ingest', 'tuya-poller', 'xiaomi-x10', 'gree-climate', 'ha-growatt-poller'):
            self.assertEqual((ROOT/'apps'/folder/'mqtt_credentials.py').read_bytes(), source)
        self.assertIn('mqtt_credentials.py', (ROOT/'apps/hc_ingest/Dockerfile').read_text())

    def test_prepare_package_is_new_private_and_not_applied(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'candidate'
            result = prepare_module.prepare(root, esp_ip='192.168.1.179')
            self.assertFalse(result['applied']);self.assertFalse(result['esp_ip_confirmed'])
            self.assertTrue(result['passwords_need_hashing'])
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            acl = (root/'legacy.acl').read_text()
            self.assertNotIn('zigbee', acl);self.assertNotIn('topic readwrite #', acl)
            self.assertIn('topic read homecontrol/cmd/irrigation/esp-irrigation-1/#', acl)
            self.assertIn('127.0.0.1:1884:1884', (root/'compose.override.json').read_text())
            dashboard=(root/'dashboard-client.env').read_text()
            self.assertIn('MQTT_USERNAME=hc_dashboard', dashboard)
            self.assertIn('MQTT_PORT=21884', dashboard)
            self.assertEqual((root/'dashboard-client.env').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):prepare_module.prepare(root)

    def test_unsafe_irrigation_id_and_address_are_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'candidate'
            for options in ({'device':'a/#'}, {'esp_ip':'0.0.0.0'}, {'esp_ip':'127.0.0.1'}):
                with self.subTest(options=options), self.assertRaises(ValueError):prepare_module.prepare(root, **options)
                self.assertFalse(root.exists())

    def test_packages_cannot_put_credentials_into_exported_source(self):
        for folder in ('infra', 'apps', 'scripts', 'homeassistant', 'docs'):
            with self.subTest(folder=folder), self.assertRaises(ValueError):
                prepare_module.prepare(ROOT/folder/'hc41-secret-package-must-not-exist')

    def test_optional_grott_profile_is_not_activated_or_verbose(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'candidate';prepare_module.prepare(root)
            config=json.loads((root/'compose.override.json').read_text())
            self.assertNotIn('growatt-grott', config['services'])
            self.assertIn('gverbose=False', (root/'grott.optional.env').read_text())

    def test_explorer_is_read_only_and_has_a_separate_private_profile(self):
        import json
        rules,_=prepare_module.access_rules('esp-irrigation-1')
        self.assertEqual(rules['explorer'], [('read','homecontrol/#'),('read','zigbee/#'),('read','$SYS/broker/#')])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'candidate';prepare_module.prepare(root)
            path=root/'mqtt-explorer.connection.json';profile=json.loads(path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(profile['username'],'hc_explorer')
            self.assertEqual((profile['host'],profile['port']),('127.0.0.1',21884))
            self.assertFalse(profile['active'])
            self.assertEqual(profile['password'],(root/'credentials/explorer.password').read_text().strip())
            self.assertNotEqual(profile['password'],(root/'credentials/dashboard.password').read_text().strip())

    def test_legacy_network_plan_covers_direct_docker_host_and_ipv6_paths(self):
        spec=importlib.util.spec_from_file_location('hc41_network', ROOT/'scripts/plan_mqtt_legacy.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.plan('192.168.1.179','172.19.0.9')
        self.assertFalse(result['applied']);self.assertFalse(result['ready_to_apply'])
        commands=result['commands_for_review_only']
        accepts=[c for c in commands if c[-1]=='ACCEPT']
        self.assertEqual(len(accepts),1);self.assertIn('192.168.1.179',accepts[0])
        self.assertTrue(any('DOCKER-USER' in c and '172.19.0.9' in c for c in commands))
        self.assertTrue(any('OUTPUT' in c and c[-1]=='DROP' for c in commands))
        self.assertTrue(any(c[0]=='ip6tables' and c[-1]=='DROP' for c in commands))


if __name__ == '__main__':unittest.main()
