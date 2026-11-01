"""Build a clean public Git snapshot; never operate on the live project tree."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

from backup_export_manifest import SOURCE_PATHS, allowed_path
from backup_protocol import atomic_json, sha256

SENSITIVE_KEYS = frozenset(('password', 'servicetoken', 'ssecurity', 'accesstoken',
                           'refreshtoken', 'apikey', 'clientsecret', 'secretkey'))


def _secret_value(value):
    if not isinstance(value, (str, int)) or not value:
        return False
    text = str(value).strip()
    return bool(text and not text.startswith(('${', '!secret', '<', 'YOUR_', 'CHANGE_')))


def check_public_file(path):
    # Binary/encrypted assets are not decoded. A private-key header is always
    # rejected, regardless of filename. No values are included in errors.
    with path.open('rb') as stream:
        head = stream.read(4096)
    if re.search(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----', head):
        raise ValueError('Private key in public export: ' + path.name)
    if path.suffix.lower() != '.json' or path.stat().st_size > 8 * 1024 * 1024:
        return
    try:
        data = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        return  # Source text is not presumed to be a credential file.
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub('[^a-z]', '', str(key).lower())
                if normalized in SENSITIVE_KEYS and _secret_value(item):
                    raise ValueError('Credential field in public export: ' + path.name)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(data)


def export_snapshot(base, target):
    base = Path(base).resolve()
    target = Path(target)
    if target.is_symlink():
        raise ValueError('Export target cannot be a symlink')
    target = target.resolve()
    if target == base or target in base.parents or base in target.parents or target == Path('/'):
        raise ValueError('Export target must be separate from the project')
    if target.exists() and any(target.iterdir()) and not (target / '.git').is_dir() and not (target / 'EXPORT_MANIFEST.json').is_file():
        raise ValueError('Existing nonempty export target must be a checkout or an earlier snapshot')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.hc-export-', dir=target.parent) as temporary:
        stage = Path(temporary)
        rows = []
        candidates = set()
        for source in SOURCE_PATHS:
            for path in base.glob(source):
                if path.is_symlink():
                    continue
                if path.is_dir():
                    for current, dirs, files in os.walk(path, followlinks=False):
                        current = Path(current)
                        dirs[:] = [name for name in dirs if not (current/name).is_symlink()
                                   and allowed_path((current/name).relative_to(base).as_posix() + '/placeholder')]
                        candidates.update(current/name for name in files)
                elif path.is_file():
                    candidates.add(path)
        for path in sorted(candidates):
            rel = path.relative_to(base).as_posix()
            if path.is_symlink() or not path.is_file() or not allowed_path(rel):
                continue
            out = stage / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out)
            out.chmod(stat.S_IMODE(out.stat().st_mode) & 0o777)
            check_public_file(out)
            rows.append({'path': rel, 'sha256': sha256(out)})
        atomic_json(stage/'EXPORT_MANIFEST.json', {'version': 1, 'sources': list(SOURCE_PATHS), 'files': rows})
        (stage/'.gitignore').write_text('\n'.join([
            '.env*', '*.db*', '*.sqlite*', '*.log*', '*.dump', '*.key', '*.pem',
            '*-key.txt', 'secrets.yaml*', 'secrets.yml*', '**/xiaomi_cloud_auth*', '**/multi_connector_config.json*',
            'infra/ssh/', 'node_modules/', '__pycache__/', '.storage/',
        ]) + '\n')
        # Clearing the checkout after validation also removes already tracked
        # credentials and obsolete files from the next git add -A snapshot.
        target.mkdir(exist_ok=True)
        for child in target.iterdir():
            if child.name == '.git':
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        for child in stage.iterdir():
            shutil.move(str(child), target/child.name)
    return {'files': len(rows), 'sources': list(SOURCE_PATHS), 'manifest': str(target/'EXPORT_MANIFEST.json')}


def stage_snapshot(target):
    """Stage the validated export, including source files hidden by nested ignores."""
    target = Path(target)
    manifest = json.loads((target / 'EXPORT_MANIFEST.json').read_text())
    expected = {'.gitignore', 'EXPORT_MANIFEST.json'}
    for row in manifest['files']:
        relative = row['path']
        path = target / relative
        if not allowed_path(relative) or path.is_symlink() or not path.is_file():
            raise ValueError('Invalid public export entry')
        if sha256(path) != row['sha256']:
            raise ValueError('Public export changed before Git staging')
        check_public_file(path)
        expected.add(relative)
    # Export has already cleared this dedicated checkout and rejected credentials.
    # Force is local staging only, never a force push.
    subprocess.run(['git', '-C', str(target), 'add', '--all', '--force', '--', '.'], check=True)
    actual = set(subprocess.check_output(['git', '-C', str(target), 'ls-files', '-z']).decode().rstrip('\0').split('\0'))
    if actual != expected:
        raise ValueError('Git index differs from the validated export manifest')
    return {'staged_files': len(actual)}


def secrets_manifest(base, output):
    base = Path(base).resolve()
    original = base/'secrets/manifest.txt'
    lines = original.read_text().splitlines()
    settings_path = base / 'backups/backup_settings.json'
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        if settings.get('backup_target') == 'router_ftp':
            from router_backup import validate
            validate(settings)
            lines.extend([settings['router_rclone_config'], settings['restic_password_file']])
    auth = base/'apps/xiaomi-x10/x10_maps'
    for path in sorted(auth.glob('xiaomi_cloud_auth*')):
        if path.is_file() and not path.is_symlink():
            lines.append(str(path))
    Path(output).write_text('\n'.join(dict.fromkeys(lines)) + '\n')
    Path(output).chmod(0o600)
