#!/usr/bin/env python3
"""Guard the already authorized reboot after the accepted host update."""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import traceback
import uuid

sys.dont_write_bytecode = True
STATE = Path('/srv/docker/homecontrol/maintenance/host-update-20261103-execution')
BOOT_ID = Path('/proc/sys/kernel/random/boot_id')
EXECUTOR_SHA = '09b8cd6c55432c7f5363d15ed0084ab6ecd9c792b2adab0c8dde5c36eb0ec0af'


def validate_boot(config, defaults, environment, kernel, root_uuid):
    if not re.search(r'^GRUB_DEFAULT=0\s*$', defaults, re.M):
        raise ValueError('GRUB default is not the reviewed first entry')
    if any(environment.get(k) for k in ('next_entry', 'prev_saved_entry', 'initrdfail', 'prev_entry')):
        raise ValueError('GRUB has a pending override or recovery entry')
    before, separator, first = config.partition('\nmenuentry ')
    if not separator or 'set default="0"' not in before:
        raise ValueError('Unexpected GRUB default selection')
    first = first.partition('\n}')[0]
    linux = re.findall(r'^\s*linux\s+(\S+)\s+([^\n]+)$', first, re.M)
    initrd = re.findall(r'^\s*initrd\s+(\S+)\s*$', first, re.M)
    if (len(linux) != 1 or linux[0][0] != '/boot/vmlinuz-' + kernel
            or 'root=UUID=' + root_uuid not in linux[0][1].split()
            or initrd != ['/boot/initrd.img-' + kernel]):
        raise ValueError('First GRUB entry differs from the reviewed kernel/root')


def validate_receipts(accepted, before, proof, current_boot):
    if (accepted.get('ok') is not True or accepted.get('state') != 'upgraded_pending_reboot'
            or accepted.get('reboot_performed') is not False
            or accepted.get('boot_id') != current_boot or before.get('boot_id') != current_boot):
        raise ValueError('Upgrade receipt does not match this pending reboot')
    if not (proof.get('ok') is True and proof.get('run_id') and proof.get('snapshot_id')
            and proof.get('archive_sha256') and proof.get('restore') == 'verified'
            and proof.get('database') == 'verified'):
        raise ValueError('Mandatory fresh backup/restore proof missing')


def perform(executor):
    saved = {}; hostops_stopped = False; requested = False
    executor.LOG = (STATE / ('reboot-' + uuid.uuid4().hex + '-private.log')).open('x')
    try:
        with ExitStack() as stack:
            handle = stack.enter_context((STATE / 'execution.lock').open('a'))
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (STATE / 'reboot-request.json').exists(): raise ValueError('Reboot already requested; inspect its receipt')
            check = executor.checks()
            before = executor.read(STATE / 'before.json')
            current_boot = BOOT_ID.read_text().strip()
            validate_receipts(executor.read(STATE / 'upgrade-success.json'), before,
                              executor.read(STATE / 'pre-proof.json'), current_boot)
            executor.phase('reboot_preflight')
            check.main('before-reboot')
            executor.idle(); executor.physical_guard(check)
            executor.common_locks(stack)
            if executor.firewall() != executor.read(STATE / 'firewall-before.json'):
                raise ValueError('MQTT firewall changed before reboot')
            executor.device_connections()
            executor.call(['/usr/bin/python3', '/usr/local/lib/homecontrol-backup-storage/migrate.py', 'check'])
            environment = dict(line.split('=', 1) for line in executor.call(
                ['grub-editenv', '/boot/grub/grubenv', 'list']).splitlines() if '=' in line)
            kernel = before['next_kernel']
            validate_boot(Path('/boot/grub/grub.cfg').read_text(), Path('/etc/default/grub').read_text(),
                          environment, kernel, before['root_uuid'])
            if executor.call(['dpkg', '--verify', 'linux-image-' + kernel]).strip():
                raise ValueError('Installed kernel package verification differs')
            files = [Path('/boot') / (prefix + name) for name in (kernel, before['kernel'])
                     for prefix in ('vmlinuz-', 'initrd.img-')]
            if any(not path.is_file() or path.stat().st_size < 1024 ** 2 for path in files):
                raise ValueError('New or recovery kernel/initrd missing')
            executor.write(STATE / 'reboot-boot-files.json', {str(path): executor.sha(path) for path in files})
            saved = executor.pause()
            executor.call(['systemctl', 'stop', 'homecontrol-hostops.service'], timeout=240)
            hostops_stopped = True
            executor.idle(); executor.physical_guard(check)
            executor.write(STATE / 'reboot-request.json', {
                'state': 'dispatching', 'boot_id_before': current_boot, 'expected_kernel': kernel})
            executor.say('A reboot kapui teljesülnek. Szabályos újraindítás indul; az SSH-kapcsolat megszakad.')
            # Let systemd/Docker stop running containers during shutdown. A manual
            # docker stop would suppress their unless-stopped boot startup.
            try: executor.call(['systemctl', 'reboot'], timeout=30)
            except BaseException:
                executor.write(STATE / 'reboot-dispatch-error.json', {'state': 'dispatch_result_unknown'})
                raise
            requested = True
            executor.write(STATE / 'reboot-request.json', {
                'state': 'requested', 'boot_id_before': current_boot, 'expected_kernel': kernel})
    except BaseException as error:
        traceback.print_exc(file=executor.LOG); executor.LOG.flush()
        executor.write(STATE / 'reboot-failure.json', {'error_type': type(error).__name__,
            'phase': executor.PHASE, 'condition': str(error) if isinstance(error, ValueError) else 'See private log'})
        executor.say('A reboot indítása megállt: ' + type(error).__name__ + '. A privát napló megőrizve.')
        raise
    finally:
        if not requested and not (STATE / 'reboot-request.json').exists():
            if hostops_stopped: executor.call(['systemctl', 'start', 'homecontrol-hostops.service'])
            if saved: executor.resume(saved)
        executor.LOG.close()


def main():
    os.umask(0o077)
    if sys.argv[1:] != ['reboot']: raise ValueError('Usage: reboot.py reboot')
    if os.geteuid() != 0: raise PermissionError('Local sudo authentication required')
    info = STATE.stat()
    if STATE.is_symlink() or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('Root-owned private execution state required')
    code = STATE / 'execute.py'
    if code.is_symlink() or hashlib.sha256(code.read_bytes()).hexdigest() != EXECUTOR_SHA:
        raise ValueError('Accepted private executor changed')
    spec = importlib.util.spec_from_file_location('accepted_host_update_executor', code)
    executor = importlib.util.module_from_spec(spec); spec.loader.exec_module(executor)
    def interrupted(signum, frame): raise InterruptedError('Reboot client interrupted')
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM): signal.signal(signum, interrupted)
    perform(executor)


if __name__ == '__main__': main()
