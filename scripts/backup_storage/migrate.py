#!/usr/bin/env python3
"""Guarded /var backup storage migration. No live action without apply/rollback."""
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout import (PINNED, StorageError, attributes, cleanup_verified_duplicates, copy_tree, digest,
                    inventory, no_symlinks, placeholders, require, verify_copy, write_json)

BASE = Path('/srv/docker/homecontrol')
PACKAGE = BASE / 'backups/releases/hc-backup-storage-20261103'
RESERVE = 30 * 1024 ** 3
WATCHERS = ('homecontrol-backup.timer', 'homecontrol-ai-weekly-backup.timer',
            'homecontrol-restic-check.timer', 'homecontrol-log-maintenance.timer',
            'homecontrol-backup-apply.path', 'homecontrol-full-ai-backup-request.path',
            'homecontrol-post-boot-health.timer')
BUSY = ('homecontrol-backup.service', 'homecontrol-ai-weekly-backup.service',
        'homecontrol-restic-check.service', 'homecontrol-log-maintenance.service',
        'homecontrol-backup-apply.service', 'homecontrol-full-ai-backup-request.service',
        'homecontrol-r21-acceptance-backup.service', 'homecontrol-r21-precheck-diagnosis.service')
GUARDED = ('docker.service', 'homecontrol-hostops.service', *BUSY[:6])


@dataclass
class Paths:
    base: Path = BASE
    storage: Path = Path('/var/lib/homecontrol-backup-storage')
    unit_root: Path = Path('/etc/systemd/system')
    helper: Path = Path('/usr/local/lib/homecontrol-backup-storage')
    var: Path = Path('/var')

    @property
    def source(self): return self.base / 'backups'
    @property
    def legacy(self): return self.base / '.backups-before-var-20261103'
    @property
    def data(self): return self.storage / 'data'
    @property
    def state(self): return self.storage / 'state'


def mount_name(path):
    return subprocess.check_output(['systemd-escape', '--path', '--suffix=mount', str(path)], text=True).strip()


def is_mounted(path):
    # Path.is_mount() always returns False for bind-mounted regular lock files.
    wanted = str(Path(path).absolute())
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        target = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), line.split()[4])
        if target == wanted: return True
    return False


def unit_files(p):
    base = mount_name(p.source)
    units = {}
    for name in ('', *PINNED):
        where = p.source / name
        what = p.legacy / name if name else p.data
        dependency = 'Requires=' + base + '\nAfter=' + base + '\n' if name else ''
        units[mount_name(where)] = ('[Unit]\nDescription=HomeControl backup storage\n' + dependency
            + 'RequiresMountsFor=' + str(what) + '\nBefore=docker.service homecontrol-hostops.service\n'
            + '[Mount]\nWhat=' + str(what) + '\nWhere=' + str(where)
            + '\nType=none\nOptions=bind\n[Install]\nWantedBy=local-fs.target\n')
    names = ' '.join(units)
    for service in GUARDED:
        mounts_only = service in ('docker.service', 'homecontrol-hostops.service')
        units[service + '.d/hc-backup-storage.conf'] = ('[Unit]\nRequires=' + names + '\nAfter=' + names
            + '\n[Service]\nExecStartPre=/usr/bin/python3 ' + str(p.helper / 'migrate.py')
            + ' check' + (' --mounts-only' if mounts_only else '') + '\n')
    return units


def call(args, *, allowed=(0,), timeout=180):
    env = {k: v for k, v in os.environ.items() if k not in ('DOCKER_CONTEXT', 'DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')}
    env['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, env=env, timeout=timeout)
    if result.returncode not in allowed:
        raise RuntimeError('Storage operation failed: ' + str(args[0]))
    return result


class Host:
    def active(self, name): return call(['systemctl', 'is-active', '--quiet', name], allowed=(0, 3, 4)).returncode == 0
    def stop(self, name): call(['systemctl', 'stop', name], timeout=180)
    def start(self, name): call(['systemctl', 'start', name], timeout=180)
    def reload(self): call(['systemctl', 'daemon-reload'])
    def enable(self, name): call(['systemctl', 'enable', name])
    def disable(self, name): call(['systemctl', 'disable', name], allowed=(0, 1))
    def backend_stop(self): call(['docker', 'stop', '--time', '60', 'homecontrol-backend'], timeout=90)
    def backend_start(self): call(['docker', 'start', 'homecontrol-backend'])
    def inspect(self, names): return json.loads(call(['docker', 'inspect', *names]).stdout)

    def idle(self):
        require(not any(self.active(name) for name in BUSY), 'Active backup or restore worker')
        for path in Path('/var/lib/homecontrol-hostops/jobs').glob('*.json'):
            no_symlinks(path)
            require(json.loads(path.read_text()).get('state') not in ('queued', 'running'), 'A host operation is queued or running')

    def daemon_mounts_ready(self, p):
        pid = call(['systemctl', 'show', 'docker.service', '--property=MainPID', '--value']).stdout.strip()
        require(pid.isdecimal() and int(pid) > 1, 'Cannot identify the Docker daemon mount namespace')
        for name in ('', 'ai-backup.lock', 'homecontrol-backup.lock'):
            path = p.source / name; info = path.stat()
            observed = call(['nsenter', '--target', pid, '--mount', '--', 'stat', '-Lc', '%d:%i', path]).stdout.strip()
            require(observed == '{}:{}'.format(info.st_dev, info.st_ino), 'Docker daemon does not see the new backup mounts')

    def guard(self, p, plan, allow_stopped_backend=False):
        marker = json.loads((p.base / 'infra/access-release.json').read_text())
        require(marker['release'] == plan['active_release'], 'Application release changed since storage preparation')
        backend_running = False
        for row in self.inspect(plan['containers']):
            name = row['Name'].lstrip('/')
            require({'id': row['Id'], 'image': row['Image']} == plan['containers'][name], 'Container changed since storage preparation')
            if name == 'homecontrol-backend': backend_running = row['State']['Running']
            allowed_stopped = name == 'homecontrol-adminer' or (name == 'homecontrol-backend' and allow_stopped_backend)
            require(allowed_stopped or row['State']['Running'], 'Application component is stopped')
            if row['State']['Running']:
                require(row['State'].get('Health', {}).get('Status') in (None, 'healthy'), 'Application component is unhealthy')
        command = ['docker', 'exec', '-i', 'homecontrol-postgres', 'sh', '-c',
                   'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
        sql = "SELECT (SELECT count(*) FROM hc.irrigation_manual_session WHERE status IN ('starting','running','stop_failed')) + (SELECT count(*) FROM hc.irrigation_solar_pump_run WHERE status='running');"
        result = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=30)
        require(result.returncode == 0 and result.stdout.strip() == '0', 'Active irrigation session or unavailable database')
        if backend_running:
            with urllib.request.urlopen('http://127.0.0.1:5000/api/xiaomi-x10/state', timeout=5) as response:
                require(str(json.load(response).get('robot_state')) in ('6', '13'), 'Robot must be idle or charging')

    def healthy(self, p, plan):
        for _ in range(90):
            try:
                self.guard(p, plan)
                with urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3) as response:
                    require(json.load(response).get('ok') is True, 'Backend readiness failed')
                with urllib.request.urlopen('http://127.0.0.1:5000/api/deployment/status', timeout=3) as response:
                    policy = json.load(response)
                    require(policy.get('ai_enabled') is False and policy.get('router_backup_enabled') is True, 'AI/router policy changed')
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError('Backend did not recover after storage switch')


def common_locks(p, stack, root=None):
    result = {}
    for name in ('ai-backup.lock', 'homecontrol-backup.lock'):
        path = (root or p.source) / name; no_symlinks(path)
        require(path.is_file(), 'Existing common lock file is missing')
        stream = stack.enter_context(path.open('a'))
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result[name] = (os.fstat(stream.fileno()).st_dev, os.fstat(stream.fileno()).st_ino)
    return result


def verify_mounts(p, locks=None, strict_device=True):
    for name in ('', *PINNED):
        target = p.source / name; original = p.legacy / name if name else p.data
        no_symlinks(target); no_symlinks(original)
        require(is_mounted(target) and os.path.samefile(target, original), 'Missing or incorrect backup storage mount')
    require(p.data.stat().st_dev == p.var.stat().st_dev and p.data.stat().st_dev != p.legacy.stat().st_dev,
            'Backup data is not on the separate /var filesystem')
    if locks:
        for name, wanted in locks.items():
            info = (p.source / name).stat()
            require(info.st_ino == wanted[1] and (not strict_device or info.st_dev == wanted[0]), 'Common lock inode changed')


def check(p, mounts_only=False):
    marker = json.loads((p.state / 'migration.json').read_text())
    require(marker['phase'] in ('mounted', 'healthy', 'complete'), 'Backup storage is not committed')
    # Device major/minor numbers may change across boots; inode and source/target
    # identity still have to match. The actual cutover checks both device+inode.
    verify_mounts(p, marker['lock_inodes'], strict_device=False)
    if not mounts_only:
        require(not os.statvfs(p.source).f_flag & os.ST_RDONLY, 'Backup filesystem is read-only')
        sizes = []
        for receipt in p.source.glob('homecontrol_*.tar.gz.complete.json'):
            value = json.loads(receipt.read_text())
            if value.get('completed') is True: sizes.append(value['size_bytes'])
        needed = RESERVE + 2 * max(sizes or [3 * 1024 ** 3])
        require(shutil.disk_usage(p.source).free >= needed, 'Backup storage has insufficient space above the 30 GiB reserve')
    return {'ok': True, 'phase': marker['phase'], 'backup_path': str(p.source), 'data_path': str(p.data),
            'free_bytes': shutil.disk_usage(p.source).free, 'reserve_bytes': RESERVE}


class Migration:
    def __init__(self, p, host, plan):
        self.p, self.host, self.plan = p, host, plan
        self.record = {'phase': 'preparing', 'watchers': {}, 'hostops_active': False, 'backend_stopped': False}

    def phase(self, value):
        self.record['phase'] = value
        self.record['timestamp'] = datetime.now(timezone.utc).isoformat()
        write_json(self.p.state / 'migration.json', self.record)
        print('Tárhely-átállítás: ' + value, flush=True)

    def pause(self):
        self.record['watchers'] = {name: self.host.active(name) for name in WATCHERS}
        self.record['hostops_active'] = self.host.active('homecontrol-hostops.service')
        for name, active in self.record['watchers'].items():
            if active: self.host.stop(name)
        if self.record['hostops_active']: self.host.stop('homecontrol-hostops.service')
        require(not any(self.host.active(name) for name in BUSY), 'Active backup or restore worker')

    def resume(self):
        if self.record['hostops_active']: self.host.start('homecontrol-hostops.service')
        for name, active in self.record['watchers'].items():
            if active: self.host.start(name)

    def install_units(self):
        for name, text in unit_files(self.p).items():
            path = self.p.unit_root / name
            require(not path.exists() and not path.is_symlink(), 'Existing storage unit requires inspection')
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name('.storage-unit-' + uuid.uuid4().hex)
            try:
                with temporary.open('x') as stream:
                    os.fchmod(stream.fileno(), 0o644); stream.write(text); stream.flush(); os.fsync(stream.fileno())
                os.link(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        self.host.reload()

    def remove_units(self):
        files = unit_files(self.p)
        for name, text in files.items():
            path = self.p.unit_root / name
            if path.exists(): require(path.read_text() == text, 'Storage unit changed; rollback refused')
        # Remove service dependencies before stopping mounts; Docker must stay up.
        for name in files:
            if name.endswith('.conf'): (self.p.unit_root / name).unlink(missing_ok=True)
        self.host.reload()
        for name in reversed(['', *PINNED]):
            unit = mount_name(self.p.source / name)
            self.host.disable(unit)
            if is_mounted(self.p.source / name): self.host.stop(unit)
            (self.p.unit_root / unit).unlink(missing_ok=True)
        self.host.reload()

    def apply(self):
        p = self.p
        for path in (p.source, p.storage, p.legacy, p.helper): no_symlinks(path)
        require(not is_mounted(p.source) and not p.legacy.exists() and not p.storage.exists() and not p.helper.exists(),
                'Storage migration already exists or destination is not empty')
        require(p.source.stat().st_dev != p.var.stat().st_dev, '/var is not a separate filesystem')
        for name in PINNED:
            path = p.source / name; no_symlinks(path)
            require(path.is_dir() if name in ('releases', 'ai-control') else path.is_file(), 'Missing pinned backup path')
            require(path.stat().st_dev == p.source.stat().st_dev, 'Unexpected existing pinned filesystem')
        require(not os.statvfs(p.var).f_flag & os.ST_RDONLY, '/var is read-only; migration refused')
        require(shutil.disk_usage(p.var).free > RESERVE + 8 * 1024 ** 3, '/var cannot provide the reserve and migration buffer')
        for name in unit_files(p):
            path = p.unit_root / name; no_symlinks(path)
            require(not path.exists(), 'Existing storage unit requires inspection before migration')
        self.host.guard(p, self.plan)
        self.host.idle()
        p.state.mkdir(mode=0o700, parents=True); p.storage.chmod(0o700)
        write_json(p.state / 'plan.json', self.plan)
        self.phase('preparing')
        try:
            with ExitStack() as stack:
                self.record['lock_inodes'] = common_locks(p, stack)
                self.host.idle()
                self.pause()
                self.host.guard(p, self.plan)
                self.phase('writers_paused')
                snapshot = inventory(p.source)
                write_json(p.state / 'original-tree.json', snapshot)
                require(shutil.disk_usage(p.var).free >= snapshot['unique_file_bytes'] + RESERVE + 8 * 1024 ** 3,
                        '/var cannot hold the copied tree and 30 GiB reserve')
                p.data.mkdir(); placeholders(p.data, p.source)
                self.phase('copying')
                copy_tree(p.source, p.data)
                proof = verify_copy(snapshot, p.data)
                write_json(p.state / 'copy-proof.json', proof)
                self.phase('copied_verified')
                require(inventory(p.source) == snapshot, 'Backup source changed during the verified copy')
                self.host.guard(p, self.plan)
                p.helper.mkdir(mode=0o755, parents=True); p.helper.chmod(0o755)
                for name in ('migrate.py', 'layout.py'):
                    shutil.copyfile(Path(__file__).with_name(name), p.helper / name)
                    (p.helper / name).chmod(0o644)
                write_json(p.state / 'helper-sha256.json', {name: digest(p.helper / name) for name in ('migrate.py', 'layout.py')})
                self.host.backend_stop(); self.record['backend_stopped'] = True
                p.source.rename(p.legacy); p.source.mkdir(mode=0o700)
                self.phase('source_renamed')
                self.install_units()
                for name in ('', *PINNED): self.host.start(mount_name(p.source / name))
                verify_mounts(p, self.record['lock_inodes'])
                self.host.daemon_mounts_ready(p)
                self.phase('mounted')
                if self.record['hostops_active']: self.host.start('homecontrol-hostops.service')
                self.host.backend_start(); self.record['backend_stopped'] = False
                self.host.healthy(p, self.plan)
                self.phase('healthy')
                cleanup = cleanup_verified_duplicates(p.legacy, p.data, snapshot)
                write_json(p.state / 'source-duplicate-cleanup.json', cleanup)
                for name in ('', *PINNED): self.host.enable(mount_name(p.source / name))
                self.phase('complete')
                result = check(p)
                write_json(p.state / 'result.json', {**result, 'active_release': self.plan['active_release'], 'application_images_changed': False})
            self.resume()
            print(json.dumps(result, indent=2), flush=True)
        except BaseException as error:
            detail = {'error_type': type(error).__name__, 'detail': str(error)}
            for field in ('stdout', 'stderr'):
                value = getattr(error, field, '') or ''
                detail[field] = value.decode(errors='replace') if isinstance(value, bytes) else value
            write_json(p.state / 'error.json', detail)
            if p.legacy.exists():
                self.rollback()
            else:
                if self.record['backend_stopped']:
                    self.host.backend_start(); self.record['backend_stopped'] = False
                self.resume(); self.phase('failed_before_switch')
            raise

    def rollback(self):
        p = self.p
        if (p.state / 'migration.json').exists(): self.record = json.loads((p.state / 'migration.json').read_text())
        require(p.legacy.is_dir(), 'Original pinned backup tree is missing')
        saved_watchers, saved_hostops = self.record['watchers'], self.record['hostops_active']
        with ExitStack() as stack:
            common_locks(p, stack, root=p.legacy)
            self.host.idle()
            self.pause()
            self.record['watchers'], self.record['hostops_active'] = saved_watchers, saved_hostops
            try:
                if is_mounted(p.source):
                    current = inventory(p.data)
                    present = inventory(p.legacy)
                    changed = [row['bytes'] for name, row in current['entries'].items() if row['type'] == 'file'
                               and (name not in present['entries'] or present['entries'][name].get('sha256') != row['sha256'])]
                    require(shutil.disk_usage(p.legacy).free >= sum(changed) + 2 * 1024 ** 3,
                            'Rollback data no longer fits /srv; working /var copy retained')
                    copy_tree(p.data, p.legacy); verify_copy(current, p.legacy)
            except BaseException:
                self.resume()
                raise
            if not self.record.get('backend_stopped'):
                self.host.backend_stop(); self.record['backend_stopped'] = True
            self.remove_units()
            if not p.source.exists(): p.source.mkdir(mode=0o700)
            require(not is_mounted(p.source) and not any(p.source.iterdir()), 'Original mount point is not empty')
            p.source.rmdir(); p.legacy.rename(p.source)
            self.phase('rolled_back')
            self.host.backend_start(); self.record['backend_stopped'] = False
        self.resume(); self.host.healthy(p, self.plan)
        self.phase('rolled_back')


def verify_package():
    receipt = json.loads((PACKAGE / 'acceptance.json').read_text())
    require(receipt.get('ok') is True, 'Storage package is not accepted')
    for name, expected in receipt['sha256'].items():
        path = PACKAGE / name; no_symlinks(path)
        require(digest(path) == expected, 'Storage package changed')
    return json.loads((PACKAGE / 'plan.json').read_text())


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'rollback', 'check'))
    parser.add_argument('--mounts-only', action='store_true')
    args = parser.parse_args()
    require(os.geteuid() == 0, 'Use local sudo; host permissions are never bypassed')
    p = Paths()
    if args.action == 'check': print(json.dumps(check(p, args.mounts_only))); return
    host = Host()
    if args.action == 'rollback':
        hashes = json.loads((p.state / 'helper-sha256.json').read_text())
        for name, expected in hashes.items():
            require(digest(Path(__file__).with_name(name)) == expected, 'Installed rollback helper changed')
        plan = json.loads((p.state / 'plan.json').read_text())
        plan = {'active_release': json.loads((p.base / 'infra/access-release.json').read_text())['release'],
                'containers': {row['Name'].lstrip('/'): {'id': row['Id'], 'image': row['Image']}
                               for row in host.inspect(plan['containers'])}}
        host.guard(p, plan, allow_stopped_backend=True)
    else:
        plan = verify_package()
    migration = Migration(p, host, plan)
    operator = Path('/run/lock/homecontrol-backup-storage.lock'); no_symlinks(operator)
    fd = os.open(operator, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as stream:
        info = os.fstat(stream.fileno())
        require(info.st_uid == 0 and info.st_mode & 0o077 == 0 and info.st_nlink == 1, 'Unsafe storage operator lock')
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'apply': migration.apply()
        else: migration.rollback()


if __name__ == '__main__':
    for interrupt in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(interrupt, lambda *_: (_ for _ in ()).throw(InterruptedError('Terminated')))
    try: main()
    except (Exception, KeyboardInterrupt) as error:
        reason = str(error) if isinstance(error, StorageError) else type(error).__name__
        if Paths().state.exists(): log = Paths().state / 'cli-error.json'
        elif (PACKAGE / 'private').is_dir(): log = PACKAGE / 'private/preflight-error.json'
        else: log = Path('/run/homecontrol-backup-storage-error.json')
        if os.geteuid() == 0:
            try:
                no_symlinks(log.parent)
                write_json(log, {'error_type': type(error).__name__, 'detail': str(error),
                                 'timestamp': datetime.now(timezone.utc).isoformat()})
            except Exception:
                pass
        print('A tárhelyművelet megállt: ' + reason + '. Részletes privát napló: ' + str(log), file=sys.stderr)
        raise SystemExit(1)
