#!/usr/bin/env python3
"""Prepare a read-only FTP shadow in the isolated guest using the real export."""
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

LAB = Path('/lab')
INPUT = LAB / 'input'
RELEASES = ('hc-router-backup-20261101-r15', 'hc-router-backup-20261101-r16')


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def guard():
    assert os.geteuid() == 0
    assert subprocess.check_output(['hostname'], text=True).strip() == 'hc-router-restore-lab'
    assert subprocess.check_output(['systemd-detect-virt'], text=True).strip() == 'kvm'
    assert (LAB / 'os-ready').is_file()


def mount_inputs():
    INPUT.mkdir(exist_ok=True)
    if not os.path.ismount(INPUT):
        run(['mount', '-t', '9p', '-o', 'trans=virtio,version=9p2000.L,ro', 'hc_input', str(INPUT)])


def shadow_mounts():
    mount_inputs()
    settings = json.loads((INPUT / 'router-settings.json').read_text())
    target = LAB / 'ftp' / settings['router_repository_path'].lstrip('/')
    target.mkdir(parents=True, exist_ok=True)
    assert (INPUT / 'repository/locks').is_dir()
    if not os.path.ismount(target):
        run(['mount', '--bind', str(INPUT / 'repository'), str(target)])
        run(['mount', '-o', 'remount,bind,ro', str(target)])
    if not os.path.ismount(target / 'locks'):
        run(['mount', '-t', 'tmpfs', '-o', 'mode=0700,size=16m', 'tmpfs', str(target / 'locks')])
    addresses = subprocess.check_output(['ip', '-j', 'address', 'show', 'dev', 'lo'], text=True)
    if '192.168.1.1' not in addresses:
        run(['ip', 'address', 'add', '192.168.1.1/32', 'dev', 'lo'])


def setup():
    guard()
    os.umask(0o077)
    LAB.mkdir(exist_ok=True)
    mount_inputs()
    receipt = json.loads((INPUT / 'input.json').read_text())
    assert receipt['ok'] and receipt['release'] in RELEASES
    assert not Path('/srv/docker/homecontrol').exists(), 'First restore must start on an empty HC host'
    assert not subprocess.check_output(['docker', 'image', 'ls', '-q'], text=True).strip(), 'First restore requires an empty image store'
    run(['timedatectl', 'set-timezone', 'Europe/Budapest'])
    shutil.copyfile(INPUT / 'rclone', '/usr/local/bin/rclone')
    Path('/usr/local/bin/rclone').chmod(0o755)
    # Guard catch-up jobs only in this lab. Production units/settings stay intact.
    for name in ('homecontrol-backup', 'homecontrol-ai-weekly-backup',
                 'homecontrol-full-ai-backup-request', 'homecontrol-restic-check',
                 'homecontrol-log-maintenance'):
        path = Path('/etc/systemd/system') / (name + '.service.d/hc-lab.conf')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[Unit]\nConditionPathExists=/run/hc-lab-allow-backup\n')
    run(['systemctl', 'daemon-reload'])
    run(['git', 'config', '--system', '--add', 'safe.directory', str(INPUT / 'git.git')])
    run(['git', 'clone', '--no-hardlinks', str(INPUT / 'git.git'), str(LAB / 'seed-project')],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    run(['git', '-C', str(LAB / 'seed-project'), 'checkout', receipt['git_commit']],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    bundle = LAB / 'seed-project/secrets/homecontrol-secrets-latest.tar.gz.age'
    decrypted = LAB / 'seed-secrets.tar.gz'
    with decrypted.open('xb') as out:
        run(['age', '-d', '-i', str(INPUT / 'age-key.txt'), str(bundle)], stdout=out)
    run(['python3', str(LAB / 'seed-project/scripts/restore_archive.py'),
         'secrets', str(decrypted), str(LAB / 'seed-secrets')], stdout=subprocess.DEVNULL)
    decrypted.unlink()
    settings = json.loads((INPUT / 'router-settings.json').read_text())
    assert settings['router_ftp_host'] == '192.168.1.1'
    assert settings['router_ftp_port'] == 21 and not settings['router_ftp_tls']
    shadow_mounts()
    # Fixed copies of reviewed public helper code, no private values in units/argv.
    if Path(__file__).resolve() != LAB / 'setup_guest.py':
        shutil.copyfile(__file__, LAB / 'setup_guest.py')
    unit = Path('/etc/systemd/system/hc-lab-ftp.service')
    unit.write_text('[Unit]\nDescription=Isolated read-only repository shadow\n'
                    '[Service]\nExecStartPre=/usr/bin/python3 /lab/setup_guest.py mounts\n'
                    'ExecStart=/usr/bin/python3 /lab/setup_guest.py ftp\n'
                    'StandardOutput=null\nStandardError=null\n[Install]\nWantedBy=multi-user.target\n')
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'hc-lab-ftp.service'])
    (LAB / 'setup.json').write_text(json.dumps({'ok': True, 'release': receipt['release'],
        'snapshot_id': receipt['snapshot_id'], 'git_commit': receipt['git_commit'],
        'empty_initial_image_store': True, 'repository_shadow': 'read_only_with_temporary_locks',
        'production_network': False, 'production_credentials_unchanged': True}) + '\n')


def ftp():
    guard()
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    sys.path.insert(0, str(LAB / 'seed-project/scripts/router_release'))
    from diagnose import reveal
    settings = json.loads((INPUT / 'router-settings.json').read_text())
    config = configparser.ConfigParser(interpolation=None)
    config.read(LAB / 'seed-secrets' / settings['router_rclone_config'].lstrip('/'))
    authorizer = DummyAuthorizer()
    authorizer.add_user(settings['router_ftp_user'],
        reveal(config[settings['router_rclone_remote']]['pass']), str(LAB / 'ftp'), perm='elradfmwMT')
    FTPHandler.authorizer = authorizer
    FTPHandler.log = lambda *args, **kwargs: None
    FTPHandler.logline = lambda *args, **kwargs: None
    FTPServer(('192.168.1.1', 21), FTPHandler).serve_forever()


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'ftp':
        ftp()
    elif len(sys.argv) == 2 and sys.argv[1] == 'mounts':
        guard()
        shadow_mounts()
    else:
        setup()
