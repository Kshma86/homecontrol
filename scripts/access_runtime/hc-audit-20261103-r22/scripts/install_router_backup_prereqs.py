#!/usr/bin/env python3
"""Plan or install the tested rclone binary; never changes backup settings or timers."""
import argparse
import hashlib
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from urllib.request import Request, urlopen
import zipfile

VERSION = 'v1.75.2'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine())
    if platform.system() != 'Linux' or not arch:
        parser.error('Supported platforms: Linux amd64/arm64')
    target = Path('/usr/local/bin/rclone')
    filename = 'rclone-{}-linux-{}.zip'.format(VERSION, arch)
    base = 'https://github.com/rclone/rclone/releases/download/' + VERSION + '/'
    print('Tested rclone: ' + VERSION + '; install path: ' + str(target))
    print('Download: ' + base + filename)
    if not args.apply:
        print('Plan only. Use sudo python3 scripts/install_router_backup_prereqs.py --apply to install.')
        return
    if os.geteuid() != 0:
        parser.error('--apply requires root')
    if not shutil.which('restic'):
        parser.error('Install restic first; this helper only installs rclone')
    if target.exists() or target.is_symlink():
        parser.error('Install target already exists; inspect the existing rclone before replacing it')
    def fetch(name):
        request = Request(base + name, headers={'User-Agent': 'HomeControl-router-backup'})
        with urlopen(request, timeout=90) as response:
            return response.read(128 * 1024 * 1024 + 1)
    data = fetch(filename)
    if len(data) > 128 * 1024 * 1024:
        raise ValueError('Oversized rclone download')
    rows = [line.split() for line in fetch('SHA256SUMS').decode().splitlines() if line.strip()]
    expected = [row[0] for row in rows if len(row) == 2 and row[1].lstrip('*') == filename]
    if expected != [hashlib.sha256(data).hexdigest()]:
        raise ValueError('rclone SHA-256 verification failed')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        binary = archive.read('rclone-{}-linux-{}/rclone'.format(VERSION, arch))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.hc-rclone-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(binary); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o755)
        # Hard link provides atomic, exclusive publication; no existing binary is overwritten.
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    subprocess.run([str(target), 'version'], check=True)
    print('Installed. Backup settings, policy and timers were not changed.')


if __name__ == '__main__':
    main()
