#!/usr/bin/env python3
"""Control only the disposable router-restore VM, never the production system."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path('/tmp/hc-router-audit-20261101')
NAME = 'hc-router-restore-lab-20261101'
LABEL = 'ai-ssd-closure-20261101'


def call(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def inspect():
    value = json.loads(subprocess.check_output(['docker', 'inspect', NAME], text=True))[0]
    assert value['Config']['Labels'].get('hc.audit') == LABEL
    assert value['HostConfig']['NetworkMode'] == 'none'
    assert not value['HostConfig']['Privileged']
    assert value['Config']['User'] == '1000:1000'
    assert all((m['Type'] == 'bind' and m['Source'] in (str(ROOT / 'vm'), str(ROOT / 'input')))
               or (m['Type'] == 'tmpfs' and m['Destination'] in ('/tmp', '/var/lib/postgresql/data'))
               for m in value['Mounts'])
    assert all(not m['RW'] for m in value['Mounts'] if m['Destination'] == '/vm/input')
    assert not any(m['Source'] == '/var/run/docker.sock' for m in value['Mounts'])
    assert 'user,id=n0,restrict=on,hostfwd=tcp:127.0.0.1:22246-:22' in value['Args']
    return value


def ssh(args, **kwargs):
    inspect()
    return call(['docker', 'exec', '-i', NAME, 'ssh', '-i', '/vm/id_ed25519',
                 '-p', '22246', '-o', 'UserKnownHostsFile=/vm/known_hosts',
                 '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
                 '-o', 'ConnectTimeout=5', 'lab@127.0.0.1', shlex.join(args)], **kwargs)


def start():
    receipt = json.loads((ROOT / 'input/input.json').read_text())
    assert receipt['ok'] and receipt['repository_check'] == 'full_data_verified'
    marker = json.loads(Path('/srv/docker/homecontrol/infra/access-release.json').read_text())
    assert receipt['release'] == marker['release']
    assert receipt['release'] in ('hc-router-backup-20261101-r15', 'hc-router-backup-20261101-r16')
    call(['docker', 'run', '-d', '--rm', '--name', NAME, '--label', 'hc.audit=' + LABEL,
          '--network', 'none', '--user', '1000:1000', '--group-add', '108',
          '--device', '/dev/kvm', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
          '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
          '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev,size=1m',
          '--mount', 'type=bind,src=' + str(ROOT / 'vm') + ',dst=/vm',
          '--mount', 'type=bind,src=' + str(ROOT / 'input') + ',dst=/vm/input,readonly',
          'hc-router-restore-tools:20261101', 'qemu-system-x86_64',
          '-machine', 'accel=kvm', '-cpu', 'host', '-m', '6144', '-smp', '2',
          '-drive', 'file=/vm/os.qcow2,format=qcow2,if=virtio',
          '-virtfs', 'local,path=/vm/input,security_model=none,mount_tag=hc_input,readonly=on',
          '-netdev', 'user,id=n0,restrict=on,hostfwd=tcp:127.0.0.1:22246-:22',
          '-device', 'virtio-net-pci,netdev=n0', '-nographic'])
    inspect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'inspect', 'ssh'))
    parser.add_argument('command', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    if options.action == 'start':
        start()
    elif options.action == 'inspect':
        value = inspect()
        print(json.dumps({'name': NAME, 'network': 'none', 'qemu_restrict': True,
                          'uid': value['Config']['User'], 'host_docker_socket': False}))
    else:
        if not options.command:
            parser.error('ssh requires an explicit guest command')
        ssh(options.command)
