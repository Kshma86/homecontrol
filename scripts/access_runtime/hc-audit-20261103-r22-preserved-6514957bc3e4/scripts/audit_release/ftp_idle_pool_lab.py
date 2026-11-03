"""Local FTP/rclone reproduction; synthetic credentials and payloads only."""
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request


def main():
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    logging.getLogger('pyftpdlib').setLevel(logging.CRITICAL)
    results = {}
    with tempfile.TemporaryDirectory(prefix='hc-ftp-idle-lab-') as directory:
        root = Path(directory)
        (root / 'ftp').mkdir()
        auth = DummyAuthorizer()
        auth.add_user('fixture', 'fixture-password', str(root / 'ftp'), perm='elradfmwMT')
        class Handler(FTPHandler):
            authorizer = auth
            timeout = 180
        server = FTPServer(('127.0.0.1', 0), Handler)
        port = server.socket.getsockname()[1]
        thread = threading.Thread(target=server.serve_forever, kwargs={'timeout': 0.05}, daemon=True)
        thread.start()
        env = {k: v for k, v in os.environ.items() if not k.startswith(('RESTIC_', 'RCLONE_'))}
        obscure = subprocess.run(['/usr/local/bin/rclone', 'obscure', '-'], input='fixture-password',
                                 env=env, text=True, capture_output=True, check=True).stdout.strip()
        config = root / 'rclone.conf'
        config.write_text('[fixture]\ntype=ftp\nhost=127.0.0.1\nport={}\nuser=fixture\npass={}\n'.format(port, obscure))
        config.chmod(0o600)
        env['RCLONE_CONFIG'] = str(config)
        processes = []
        streams = []
        try:
            for label, idle in (('original', '1m'), ('fixed', '10s')):
                folder = root / 'ftp' / label
                (folder / 'data').mkdir(parents=True)
                (folder / 'locks').mkdir()
                (folder / 'locks' / ('b' * 64)).write_bytes(b'synthetic lock fixture')
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', 0))
                    http_port = probe.getsockname()[1]
                log = (root / (label + '.log')).open('w+')
                streams.append(log)
                command = ['/usr/local/bin/rclone', 'serve', 'restic', 'fixture:/' + label,
                           '--addr=127.0.0.1:' + str(http_port), '--log-level=ERROR',
                           '--timeout=30s', '--contimeout=10s', '--ftp-idle-timeout=' + idle,
                           '--checkers=1', '--transfers=1', '--retries=1', '--low-level-retries=1']
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
                processes.append(process)
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError('Local server failed: ' + log.read())
                    try:
                        with socket.create_connection(('127.0.0.1', http_port), timeout=0.2):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise RuntimeError('Local server startup timed out')
                        time.sleep(0.05)
                results[label] = {'url': 'http://127.0.0.1:' + str(http_port), 'idle': idle}

            def post(row, name):
                payload = ('synthetic payload ' + name).encode()
                object_id = hashlib.sha256(payload).hexdigest()
                request = urllib.request.Request(row['url'] + '/data/' + object_id, data=payload, method='POST')
                try:
                    with urllib.request.urlopen(request, timeout=15) as response:
                        code = response.status
                except urllib.error.HTTPError as error:
                    code = error.code
                return code, payload, object_id

            for label, row in results.items():
                code, _, _ = post(row, 'before')
                row['initial_upload_status'] = code
                assert code == 200, (label, code)
            time.sleep(35)
            for label, row in results.items():
                code, payload, object_id = post(row, 'after')
                row['after_35s_idle_status'] = code
                stored = root / 'ftp' / label / 'data' / object_id[:2] / object_id
                row['after_idle_content_verified'] = stored.is_file() and stored.read_bytes() == payload
                request = urllib.request.Request(row['url'] + '/locks/' + 'b' * 64, method='DELETE')
                try:
                    with urllib.request.urlopen(request, timeout=15) as response: row['lock_delete_status'] = response.status
                except urllib.error.HTTPError as error: row['lock_delete_status'] = error.code
                if code == 200:
                    with urllib.request.urlopen(row['url'] + '/data/' + object_id, timeout=15) as response:
                        row['http_readback_verified'] = response.read() == payload
                del row['url']
            for label, log in zip(results, streams):
                log.flush(); log.seek(0)
                error = log.read()
                results[label]['tcp_write_timeout'] = 'write tcp' in error and 'i/o timeout' in error
            assert results['original']['after_35s_idle_status'] == 500, results
            assert results['original']['tcp_write_timeout'], results
            assert results['fixed']['after_35s_idle_status'] == 200, results
            assert results['fixed']['after_idle_content_verified'], results
            assert results['fixed']['http_readback_verified'], results
            assert results['fixed']['lock_delete_status'] == 200, results
            print(json.dumps({'ok': True, 'network': 'loopback_only', 'router_contacted': False,
                              'timeout_seconds': 30, 'idle_gap_seconds': 35, 'results': results}, indent=2))
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            for log in streams:
                log.close()
            server.close_all(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
