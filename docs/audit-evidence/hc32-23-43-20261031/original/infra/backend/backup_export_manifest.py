"""HC-17/18 reviewed public snapshot inventory, shared with the API and exporter."""
import fnmatch
from pathlib import PurePosixPath

SOURCE_PATHS = (
    'homeassistant/config', 'homeassistant/docker-compose.yml',
    'infra/docker-compose.yml', 'infra/backend', 'infra/frontend', 'infra/db',
    'infra/proxy', 'infra/mqtt/config', 'infra/mdns',
    'apps', 'scripts', 'docs', 'secrets', '*.md',
)
DENIED_PARTS = frozenset(('.git', '.env', '__pycache__', '.cache', '.storage',
                          'node_modules', 'dist', 'build', 'deps', 'tts'))
DENIED_PREFIXES = ('infra/ssh/', 'infra/postgres/data/', 'infra/mqtt/data/',
                   'infra/mqtt/log/', 'infra/zigbee2mqtt/data/',
                   'apps/tuya-poller/logs/', 'apps/xiaomi-x10/x10_maps/captures/')
DENIED_NAMES = ('.env*', '*.db', '*.db-*', '*.sqlite*', '*.log*', '*.tar.gz',
                '*.dump', '*.key', '*.pem', '*-key.txt', '.ha_run.lock',
                'xiaomi_cloud_auth*', 'multi_connector_config.json*', 'secrets.yaml*', 'secrets.yml*',
                'credentials*.json*', 'service_account*.json*', 'passwd', 'password*')
PUBLIC_SECRET_FILES = frozenset(('.gitignore', 'README.md', 'manifest.txt', 'age-recipient.txt'))


def allowed_path(relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        return False
    if any(part in DENIED_PARTS or part.startswith('.env') for part in path.parts):
        return False
    text = path.as_posix()
    if text.startswith(DENIED_PREFIXES):
        return False
    if path.parts[0] == 'secrets':
        return len(path.parts) == 2 and (path.name in PUBLIC_SECRET_FILES
            or path.name.endswith(('.age', '.age.sha256')))
    return not any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in DENIED_NAMES)


def git_paths():
    return list(SOURCE_PATHS)
