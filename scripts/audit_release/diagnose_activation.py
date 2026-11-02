"""Read-only, secret-free diagnosis of the failed r19 activation."""
import json
import re
from pathlib import Path

BASE = Path('/srv/docker/homecontrol')
KIT = BASE / 'backups/releases/hc-audit-20261102-r19'


def main():
    error = json.loads((KIT / 'private/audit-error.json').read_text())
    detail = error.get('detail', '')
    known = detail in (
        'Scheduled backup timers are not active',
        'Deployed runtime differs from sealed source',
        'New release is not active',
        'AI/router policy changed',
    ) or bool(re.fullmatch(r'Backup unit changed: homecontrol-[a-z-]+\.(?:service|timer|path)', detail))
    result = {
        'read_only': True,
        'active_release': json.loads((BASE / 'infra/access-release.json').read_text())['release'],
        'deployment': json.loads((KIT / 'deployment-status.json').read_text()),
        'error_type': error.get('error_type'),
        'known_error': detail if known else 'unclassified; private detail withheld',
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
