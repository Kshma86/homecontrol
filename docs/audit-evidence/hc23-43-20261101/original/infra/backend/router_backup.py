"""Encrypted router storage via restic/rclone. No network or writes on import."""
import configparser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile


DEFAULTS = {
    'backup_target': 'ai_sftp',
    'git_origin_enabled': True,
    'router_ftp_host': '192.168.1.1',
    'router_ftp_user': 'kshma',
    'router_ftp_port': 21,
    'router_ftp_tls': False,
    'router_mount': '/G',
    'router_repository_path': '/G/hc-backup/restic/homecontrol',
    'router_rclone_remote': 'routerbackup',
    'router_rclone_config': '/etc/homecontrol/router-rclone.conf',
}


def is_router(settings):
    return settings.get('backup_target') == 'router_ftp'


def validate(settings):
    """Validate public settings only; backend never needs to read FTP credentials."""
    if settings.get('backup_target', 'ai_sftp') not in ('ai_sftp', 'router_ftp'):
        raise ValueError('Unknown backup target')
    if not is_router(settings):
        return
    for key in ('router_ftp_host', 'router_ftp_user'):
        text = settings.get(key, '')
        if not isinstance(text, str) or not text or any(c.isspace() or ord(c) < 32 for c in text):
            raise ValueError('Invalid router host/user')
    host = settings['router_ftp_host']
    if any(c in host for c in '/@\\') or host.startswith('-'):
        raise ValueError('Router host must be a hostname or IP, without a URL prefix')
    port = settings.get('router_ftp_port')
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('Router FTP port must be 1..65535')
    if not isinstance(settings.get('router_ftp_tls'), bool):
        raise ValueError('router_ftp_tls must be boolean')
    remote = settings.get('router_rclone_remote', '')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', remote):
        raise ValueError('Invalid rclone remote name')
    mount = PurePosixPath(settings.get('router_mount', ''))
    path = PurePosixPath(settings.get('router_repository_path', ''))
    for value in (str(mount), str(path)):
        if not value.startswith('/') or any(ord(c) < 32 for c in value) or '..' in PurePosixPath(value).parts:
            raise ValueError('Router paths must be absolute without parent traversal')
    if str(mount) == '/' or mount not in path.parents:
        raise ValueError('Repository must be inside the mounted router disk')
    config = Path(settings.get('router_rclone_config', ''))
    if not config.is_absolute() or any(ord(c) < 32 for c in str(config)):
        raise ValueError('rclone config must be an absolute path')


def repository(settings):
    validate(settings)
    return 'rclone:{}:{}'.format(settings['router_rclone_remote'], settings['router_repository_path'])


def private_text(path):
    """Refuse symlinks, public permissions, foreign owners and oversized secrets."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid not in (0, os.geteuid()):
            raise ValueError('Credential file must be private (0600) and owned by the runner or root')
        text = stream.read(65537)
        if len(text) > 65536 or not text.strip():
            raise ValueError('Empty or oversized credential file')
        return text


def require_rclone(run=subprocess.run, env=None):
    result = run(['rclone', 'version'], env=env, check=False, capture_output=True, text=True, timeout=15)
    match = re.search(r'^rclone v(\d+)\.(\d+)\.(\d+)', result.stdout, re.MULTILINE)
    if result.returncode or not match or tuple(map(int, match.groups())) < (1, 75, 2):
        raise ValueError('Router backup requires tested rclone 1.75.2 or newer; the Ubuntu 1.53 package is incompatible')


class RouterRepository:
    def __init__(self, settings, *, run=subprocess.run, cache=None):
        self.settings = {**DEFAULTS, **settings}
        validate(self.settings)
        if not is_router(self.settings):
            raise ValueError('Router target is not selected')
        self.run = run
        self.repo = repository(self.settings)
        # Do not allow ambient remote definitions/passwords to override the private config.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('RCLONE_', 'RESTIC_'))}
        self.env.update(RCLONE_CONFIG=self.settings['router_rclone_config'], RCLONE_ASK_PASSWORD='false',
                        RESTIC_REPOSITORY=self.repo,
                        RESTIC_PASSWORD_FILE=self.settings['restic_password_file'])
        if cache:
            self.env['RESTIC_CACHE_DIR'] = str(cache)
            self.env['RCLONE_CACHE_DIR'] = str(Path(cache) / 'rclone')
        self.command = ['restic', '-o', 'rclone.args=serve restic --stdio --log-level ERROR '
                        '--contimeout 10s --timeout 30s --retries 1 --low-level-retries 1 '
                        '--checkers 1 --transfers 1', '-o', 'rclone.connections=2']

    def call(self, args, *, timeout=10800):
        # Capture diagnostics privately: raw server errors/config paths never enter web output.
        result = self.run(self.command + list(args), env=self.env, check=False,
                          capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError('Restic operation failed (exit {}); repository was not reinitialized'.format(result.returncode))
        return result.stdout

    def prepare(self):
        for tool in ('restic', 'rclone'):
            if not shutil.which(tool):
                raise ValueError(tool + ' is not installed')
        require_rclone(self.run, self.env)
        if self.settings['router_ftp_tls']:
            help_result = self.run(['rclone', 'help', 'backend', 'ftp'], env=self.env,
                                   check=False, capture_output=True, text=True, timeout=15)
            if '--ftp-explicit-tls' not in help_result.stdout:
                raise ValueError('Installed rclone does not support explicit FTPS')
        private_text(self.settings['restic_password_file'])
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(private_text(self.settings['router_rclone_config']))
        section = self.settings['router_rclone_remote']
        if not config.has_section(section):
            raise ValueError('Configured rclone FTP remote is missing')
        ftp = config[section]
        if (ftp.get('type') != 'ftp' or ftp.get('host') != self.settings['router_ftp_host']
                or ftp.get('user') != self.settings['router_ftp_user']
                or ftp.get('port', '21') != str(self.settings['router_ftp_port'])
                or not ftp.get('pass') or ftp.get('tls', 'false').lower() != 'false'
                or ftp.get('explicit_tls', 'false').lower() != str(self.settings['router_ftp_tls']).lower()
                or ftp.get('no_check_certificate', 'false').lower() != 'false'):
            raise ValueError('Private FTP remote does not match the selected router settings')
        allowed = {'type', 'host', 'user', 'port', 'pass', 'tls', 'explicit_tls', 'no_check_certificate'}
        if set(ftp) - allowed:
            raise ValueError('Unexpected FTP remote options; use the setup helper')
        # Require the disk itself to exist; never recreate /G when USB storage is absent.
        result = self.run(['rclone', 'lsf', self.settings['router_rclone_remote'] + ':' + self.settings['router_mount'],
                           '--dirs-only', '--max-depth', '1', '--retries', '1', '--low-level-retries', '1'],
                          env=self.env, check=False, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise RuntimeError('Router disk is unavailable; no repository was created')

    def init(self):
        self.prepare()
        # FTP backends may require the repository's base folder before serve-restic.
        folder = self.settings['router_rclone_remote'] + ':' + self.settings['router_repository_path']
        result = self.run(['rclone', 'mkdir', folder, '--retries', '1', '--low-level-retries', '1'],
                          env=self.env, check=False, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Cannot create the router repository folder')
        # Explicit operator command only. restic refuses an existing repository.
        self.call(['init'], timeout=120)

    def check(self):
        self.prepare()
        self.call(['check', '--read-data'])

    def snapshots(self):
        rows = json.loads(self.call(['snapshots', '--json', '--tag', 'homecontrol,router-hdd'])) or []
        if not isinstance(rows, list) or any(not re.fullmatch(r'[0-9a-f]{64}', row.get('id', '')) for row in rows):
            raise ValueError('Invalid snapshot inventory')
        return rows

    def backup(self, sources, *, excludes=(), tags=()):
        self.prepare()
        # Ordinary backups require an already initialized, accessible repository.
        self.call(['snapshots', '--json'], timeout=120)
        paths = [str(Path(source).resolve(strict=True)) for source in sources]
        args = ['backup', '--json', '--tag', 'homecontrol', '--tag', 'router-hdd']
        for tag in tags:
            args += ['--tag', tag]
        for pattern in excludes:
            args += ['--exclude', str(pattern)]
        args += ['--'] + paths
        output = self.call(args)
        summaries = [json.loads(line) for line in output.splitlines() if line.strip()]
        ids = [row.get('snapshot_id', '') for row in summaries if row.get('message_type') == 'summary']
        if len(ids) != 1 or not re.fullmatch(r'[0-9a-f]{8,64}', ids[0]):
            raise ValueError('Backup returned no confirmed snapshot ID')
        if len(ids[0]) == 64:
            return ids[0]
        # Older supported restic versions print an 8-character summary ID.
        matches = [row['id'] for row in self.snapshots() if row['id'].startswith(ids[0])]
        if len(matches) != 1:
            raise ValueError('Snapshot ID prefix is missing or ambiguous')
        return matches[0]

    def retention(self):
        args = ['forget', '--tag', 'homecontrol,router-hdd', '--group-by', 'host,tags']
        for kind in ('daily', 'weekly', 'monthly'):
            count = self.settings.get('restic_keep_' + kind, {'daily': 14, 'weekly': 8, 'monthly': 6}[kind])
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 365:
                raise ValueError('Invalid restic retention')
            args += ['--keep-' + kind, str(count)]
        # Router FTP listing under parallel load previously reported existing packs
        # as missing. Never forget snapshots unless the complete data read passed.
        self.check()
        self.call(args + ['--prune'])
        self.check()

    def restore(self, snapshot_id, target, *, include=None):
        if not re.fullmatch(r'[0-9a-f]{64}', snapshot_id):
            raise ValueError('A full snapshot ID is required')
        target = Path(target)
        if not target.is_dir() or any(target.iterdir()):
            raise ValueError('Restore requires an empty staging directory')
        args = ['restore', snapshot_id, '--target', str(target)]
        if include:
            args += ['--include', include]
        self.call(args)

    def smoke(self):
        """Use a separate repository: retained random fixture proves a pinned restore."""
        from hashlib import sha256
        with tempfile.TemporaryDirectory(prefix='hc-router-smoke-') as temporary:
            work = Path(temporary)
            source = work / 'random.bin'
            source.write_bytes(os.urandom(1024 * 1024))
            snapshot_id = self.backup([source], tags=['router-probe'])
            self.check()
            target = work / 'restore'
            target.mkdir()
            self.restore(snapshot_id, target)
            restored = target / source.relative_to('/')
            if not restored.is_file() or sha256(source.read_bytes()).digest() != sha256(restored.read_bytes()).digest():
                raise ValueError('Restored router fixture does not match')
            return {'ok': True, 'snapshot_id': snapshot_id, 'sha256': sha256(source.read_bytes()).hexdigest()}
