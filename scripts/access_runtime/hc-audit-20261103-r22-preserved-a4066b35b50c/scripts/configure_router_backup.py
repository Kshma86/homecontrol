#!/usr/bin/env python3
"""Write new private router credentials and candidate settings; never activate timers."""
import argparse
import configparser
import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infra/backend'))
from router_backup import DEFAULTS, private_text, repository, validate, require_rclone


def create_private(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation: no existing password/config/settings can be overwritten.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings-out', required=True, type=Path, help='New candidate JSON; not the live settings file')
    parser.add_argument('--config', type=Path, default=Path(DEFAULTS['router_rclone_config']))
    parser.add_argument('--password-file', type=Path, default=Path('/etc/homecontrol/router-restic-password'))
    parser.add_argument('--host', default=DEFAULTS['router_ftp_host'])
    parser.add_argument('--user', default=DEFAULTS['router_ftp_user'])
    parser.add_argument('--port', type=int, default=21)
    parser.add_argument('--mount', default='/G')
    parser.add_argument('--repository-path', default=DEFAULTS['router_repository_path'])
    parser.add_argument('--tls', action='store_true')
    args = parser.parse_args()
    output = args.settings_out.resolve()
    if output == Path('/srv/docker/homecontrol/backups/backup_settings.json'):
        parser.error('Use a candidate filename; this helper does not change live backup settings')
    if not args.config.is_absolute() or not args.password_file.is_absolute():
        parser.error('Credential paths must be absolute')
    if len({output, args.config.resolve(), args.password_file.resolve()}) != 3:
        parser.error('Settings, config and password must be different files')
    if args.config.exists() or args.config.is_symlink() or output.exists() or output.is_symlink():
        parser.error('Config/settings already exists; use new paths or reuse the existing candidate')
    settings = {**DEFAULTS, 'backup_target': 'router_ftp', 'router_ftp_host': args.host,
                'router_ftp_user': args.user, 'router_ftp_port': args.port,
                'router_ftp_tls': args.tls, 'router_mount': args.mount,
                'router_repository_path': args.repository_path,
                'router_rclone_config': str(args.config), 'restic_enabled': True,
                'restic_required': True, 'restic_password_file': str(args.password_file),
                'git_origin_enabled': False, 'git_enabled': False, 'git_offsite_enabled': False,
                'ai_weekly_shutdown_after': False, 'include_gitea': False}
    validate(settings)
    settings['restic_repository'] = repository(settings)
    require_rclone()
    if not sys.stdin.isatty():
        parser.error('Run from an interactive terminal to enter the FTP password')
    if args.password_file.exists():
        private_text(args.password_file)
    password = getpass.getpass('Router FTP-jelszó (nem kerül parancssorba): ')
    if not password or any(c in password for c in '\r\n\x00'):
        parser.error('Empty password/control characters are not accepted')
    obscured = subprocess.run(['rclone', 'obscure', '-'], input=password, capture_output=True, text=True, check=True).stdout.strip()
    if not obscured:
        raise ValueError('rclone returned no obscured password')
    config = configparser.ConfigParser(interpolation=None)
    config[settings['router_rclone_remote']] = {
        'type': 'ftp', 'host': args.host, 'user': args.user, 'port': str(args.port),
        'pass': obscured, 'tls': 'false', 'explicit_tls': str(args.tls).lower(),
        'no_check_certificate': 'false'}
    import io
    text = io.StringIO()
    config.write(text)
    create_private(args.config, text.getvalue())
    if not args.password_file.exists():
        create_private(args.password_file, secrets.token_urlsafe(48) + '\n')
    create_private(output, json.dumps(settings, indent=2, ensure_ascii=False) + '\n')
    print('Candidate settings written: ' + str(output))
    print('Save the restic password file separately. Live settings and timers were not changed.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Setup failed ({}). Existing files were not replaced; check newly created files before retrying.'.format(type(error).__name__), file=sys.stderr)
        raise SystemExit(1)
