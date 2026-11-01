#!/usr/bin/env python3
"""Read-only remote diagnosis of r14: index, independent listings and pack reads."""
import base64
import configparser
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import ftplib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import uuid

BASE = Path('/srv/docker/homecontrol')
RELEASE = 'hc-router-backup-20261101-r14'
HEX = re.compile(r'[0-9a-f]{64}')


def reveal(obscured):
    # rclone v1.75.2 fs/config/obscure/obscure.go: decode in memory, never argv.
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    raw = base64.urlsafe_b64decode(obscured + '=' * (-len(obscured) % 4))
    if len(raw) < 16:
        raise ValueError('Invalid obscured password')
    key = bytes.fromhex('9c935b48730a554d6bfd7c63c886a92bd390198eb8128afbf4de162b8b95f638')
    decoder = Cipher(algorithms.AES(key), modes.CTR(raw[:16])).decryptor()
    return (decoder.update(raw[16:]) + decoder.finalize()).decode()


@contextmanager
def ftp_connection(settings, password):
    ftp = ftplib.FTP_TLS(timeout=30) if settings['router_ftp_tls'] else ftplib.FTP(timeout=30)
    try:
        ftp.connect(settings['router_ftp_host'], settings['router_ftp_port'])
        ftp.login(settings['router_ftp_user'], password)
        if settings['router_ftp_tls']:
            ftp.prot_p()
        ftp.set_pasv(True)
        yield ftp
    finally:
        ftp.close()


def native_inventory(ftp, repository):
    # NLST avoids rclone's LIST/MLSD parsing. Never traverse outside data/xx.
    data = repository + '/data'
    result = set()
    for entry in ftp.nlst(data):
        prefix = PurePosixPath(entry).name
        if re.fullmatch(r'[0-9a-f]{2}', prefix):
            for pack in ftp.nlst(data + '/' + prefix):
                name = PurePosixPath(pack).name
                if HEX.fullmatch(name) and name.startswith(prefix):
                    result.add(name)
    return result


def read_pack(ftp, repository, pack):
    if not HEX.fullmatch(pack):
        raise ValueError('Invalid pack ID')
    digest = hashlib.sha256()
    length = 0
    def receive(block):
        nonlocal length
        length += len(block)
        if length > 64 * 1024 * 1024:
            raise ValueError('Unexpectedly oversized diagnostic pack')
        digest.update(block)
    ftp.voidcmd('TYPE I')
    ftp.retrbinary('RETR ' + repository + '/data/' + pack[:2] + '/' + pack, receive)
    return {'id': pack, 'bytes': length, 'sha256_matches_name': digest.hexdigest() == pack}


def expected_packs(indexes):
    superseded = {name for index in indexes.values() for name in index.get('supersedes', [])}
    return {pack['id'] for name, index in indexes.items() if name not in superseded
            for pack in index.get('packs', []) if HEX.fullmatch(pack.get('id', ''))}


def inspect(repo, work, connect, report):
    indexes = {}
    report['phase'] = 'metadata'
    snapshots = repo.call(['--no-lock', 'snapshots', '--json'])
    (work / 'snapshots.json').write_text(snapshots)
    report['snapshot_ids'] = [item['id'] for item in json.loads(snapshots)]
    names = [line.strip() for line in repo.call(['--no-lock', 'list', 'index']).splitlines()
             if HEX.fullmatch(line.strip())]
    if not names or len(names) > 128:
        raise ValueError('Unexpected index inventory; inspect private logs')
    for name in names:
        raw = repo.call(['--no-lock', 'cat', 'index', name])
        (work / ('index-' + name + '.json')).write_text(raw)
        indexes[name] = json.loads(raw)
    expected = expected_packs(indexes)
    report['index_count'] = len(indexes)
    report['indexed_pack_count'] = len(expected)
    inventories = {}
    remote = repo.settings['router_rclone_remote'] + ':' + repo.settings['router_repository_path'] + '/data'
    for label, options in [('rclone_default', []), ('rclone_without_mlsd', ['--ftp-disable-mlsd'])]:
        report['phase'] = label
        result = repo.run(['rclone', 'lsjson', remote, '--recursive', '--files-only',
                           '--checkers', '1', '--transfers', '1', '--retries', '1',
                           '--low-level-retries', '1', *options], env=repo.env,
                          capture_output=True, text=True, timeout=600, check=False)
        if result.returncode:
            report[label] = {'exit_code': result.returncode}
            continue
        rows = json.loads(result.stdout)
        inventories[label] = {PurePosixPath(item['Path']).name for item in rows
                              if HEX.fullmatch(PurePosixPath(item['Path']).name)}
        (work / (label + '.json')).write_text(result.stdout)
    report['phase'] = 'native_ftp_nlst'
    try:
        with connect() as ftp:
            inventories['native_ftp_nlst'] = native_inventory(ftp, repo.settings['router_repository_path'])
        (work / 'native-packs.json').write_text(json.dumps(sorted(inventories['native_ftp_nlst'])))
    except (OSError, ftplib.Error) as error:
        report['native_ftp_nlst'] = {'error_type': type(error).__name__}
    missing = set()
    for label, packs in inventories.items():
        absent = expected - packs
        report[label] = {'listed_pack_count': len(packs), 'missing_indexed_pack_count': len(absent),
                         'unexpected_pack_count': len(packs - expected)}
        missing.update(absent)
        (work / (label + '-missing.json')).write_text(json.dumps(sorted(absent)))
    # Include packs reported missing by the real check, even if this listing recovers.
    for log in sorted(work.parent.glob('router-maintenance-*.log'))[-3:]:
        for prefix in re.findall(r'pack ([0-9a-f]{8,64}): does not exist', log.read_text()):
            missing.update(pack for pack in expected if pack.startswith(prefix))
    report['phase'] = 'direct_pack_reads'
    samples = sorted(missing)[:3] if missing else sorted(expected)[:3]
    report['sampled_packs'] = []
    for pack in samples:
        try:
            with connect() as ftp:
                proof = read_pack(ftp, repo.settings['router_repository_path'], pack)
        except (OSError, ftplib.Error, ValueError) as error:
            proof = {'id': pack, 'error_type': type(error).__name__}
            if isinstance(error, ftplib.Error):
                match = re.match(r'\d{3}', str(error))
                if match:
                    proof['ftp_reply_code'] = match.group()
        report['sampled_packs'].append(proof)
    report['phase'] = 'diagnosis_complete'
    report['diagnostics_completed'] = True
    report['repository_repaired'] = False
    report['remote_write_commands'] = 0


def main():
    if os.geteuid() != 0:
        raise PermissionError('A privát FTP-beállításokhoz helyi sudo szükséges.')
    sys.dont_write_bytecode = True
    os.umask(0o077)
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    kit = BASE / 'backups/releases' / RELEASE
    runtime = BASE / 'scripts/access_runtime' / RELEASE
    if json.loads((BASE / 'infra/access-release.json').read_text()).get('release') != RELEASE:
        raise ValueError('This diagnostic requires active r14')
    manifest = json.loads((kit / 'release.json').read_text())
    for name in ('infra/backend/router_backup.py',):
        if hashlib.sha256((runtime / name).read_bytes()).hexdigest() != manifest['source_sha256'][name]:
            raise ValueError('Frozen module changed')
    sys.path.insert(0, str(runtime / 'infra/backend'))
    from router_backup import RouterRepository, private_text
    settings = json.loads(private_text(BASE / 'backups/backup_settings.json'))
    if settings.get('restic_enabled') or settings.get('ai_weekly_backup_enabled'):
        raise ValueError('Suspend router backups before diagnosis')
    if (settings.get('backup_target') != 'router_ftp'
            or settings.get('router_repository_path') != '/G/hc-backup/restic/homecontrol'):
        raise ValueError('Unexpected repository')
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(private_text(settings['router_rclone_config']))
    password = reveal(config[settings['router_rclone_remote']]['pass'])
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    work = kit / 'private' / ('router-diagnosis-' + identifier)
    report_path = kit / 'evidence' / ('router-diagnosis-' + identifier + '.json')
    report = {'release': RELEASE, 'repository_healthy': False, 'diagnostics_completed': False,
              'started_at': datetime.now(timezone.utc).isoformat()}
    with (BASE / 'backups/homecontrol-backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        work.mkdir(mode=0o700)
        with (work / 'commands.log').open('x') as log, tempfile.TemporaryDirectory(prefix='hc-router-diagnose-') as cache:
            def run(args, **kwargs):
                result = subprocess.run(args, **kwargs)
                log.write('\nPhase: ' + report.get('phase', 'prepare') + '\n')
                log.write(result.stdout or '')
                log.write(result.stderr or '')
                log.flush()
                return result
            repo = RouterRepository(settings, run=run, cache=Path(cache))
            print('Csak olvasás: indexek → két rclone-lista → natív FTP-lista → közvetlen pack-visszaolvasás.', flush=True)
            try:
                repo.prepare()
                inspect(repo, work, lambda: ftp_connection(settings, password), report)
            except Exception as error:
                report['error_type'] = type(error).__name__
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['private_metadata'] = str(work)
        fd = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'w') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0 if report['diagnostics_completed'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BlockingIOError:
        raise SystemExit('Másik mentés fut; a diagnosztika nem indult el.')
    except Exception as error:
        raise SystemExit('A diagnosztika nem indult el: ' + type(error).__name__)
