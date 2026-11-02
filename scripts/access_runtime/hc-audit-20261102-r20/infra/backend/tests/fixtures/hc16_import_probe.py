"""HC-16 fresh-process import permutations and actual app auth contract, no I/O."""
import importlib
import itertools
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch


def forbidden(*args, **kwargs):
    raise AssertionError('HC-16 import/auth probe attempted external work')


def guard(event, args):
    if event in ('socket.connect', 'socket.connect_ex', 'socket.bind', 'subprocess.Popen', 'os.system', 'os.fork'):
        forbidden()
    if event == 'open':
        path, mode, flags = args
        if isinstance(path, (str, bytes)):
            if os.fsdecode(path).startswith('/srv/docker/homecontrol/'):
                forbidden()
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                forbidden()


sys.addaudithook(guard)
names = ('mower_v3_service', 'mower_v3_commands', 'mower_manual_service',
         'mower_motor_test', 'mower_parameters_service')
with patch.object(threading.Thread, 'start', side_effect=forbidden):
    orders = 0
    for order in itertools.permutations(names):
        for name in (*names, 'mower_v3_protocol'):
            sys.modules.pop(name, None)
        for name in order:
            importlib.import_module(name)
        protocol = importlib.import_module('mower_v3_protocol')
        for name in names:
            module = sys.modules[name]
            if hasattr(module, 'RoverReadError'):
                assert module.RoverReadError is protocol.RoverReadError
            if hasattr(module, 'request_id'):
                assert module.request_id is protocol.request_id
        orders += 1
    import psycopg
    with patch.object(psycopg, 'connect', side_effect=forbidden):
        # Deliberately invalid obsolete values cannot activate a browser gate.
        os.environ.update(MOWER_OPERATOR_PASSWORD_HASH='obsolete-test-value',
                          MOWER_OPERATOR_SESSION_SECRET='obsolete-test-value',
                          ROVER_API_TOKEN='a' * 64, ROVER_API_TOKEN_FILE='')
        import app as module
        from settings import BackendSettings
        settings = BackendSettings()
        assert not hasattr(settings, 'mower_operator_password_hash')
        assert not hasattr(settings, 'mower_operator_session_secret')
        assert settings.rover_api_token == 'a' * 64
        assert 'a' * 64 not in repr(settings)
        assert module._mower_operator_auth.superuser is True
        assert module._startup_service is None
        module.get_startup_service = lambda: SimpleNamespace(ensure_started=lambda: None)
        module.record_api_request = lambda response: None
        client = module.app.test_client()
        status = client.get('/api/mower/v3/operator')
        assert status.status_code == 200
        assert status.json == dict(ok=True, configured=True, authenticated=True,
                                   superuser=True, session_seconds=None)
        login = client.post('/api/mower/v3/operator/login', headers={'Origin': 'http://localhost'})
        assert login.status_code == 200 and login.json == status.json
        assert not login.headers.get('Set-Cookie')
        rejected = 0
        for origin in ('https://evil.test', '', 'http://localhost.evil.test', 'http://user@localhost'):
            for path in ('operator/login', 'operator/logout', 'command', 'stop',
                         'parameters/drafts/hc16-test', 'motor-test/config', 'motor-test/apply'):
                response = client.post('/api/mower/v3/' + path, json={}, headers={'Origin': origin})
                assert response.status_code == 403, (path, origin, response.status_code)
                assert response.json['code'] == 'ORIGIN_REJECTED'
                rejected += 1
        assert 'a' * 64 not in status.get_data(as_text=True) + login.get_data(as_text=True)
print(json.dumps(dict(import_orders=orders, rejected_origins=rejected, external_work=False,
                      single_superuser=True, obsolete_settings_absent=True, native_token_private=True)))
