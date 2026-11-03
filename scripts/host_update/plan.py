"""Read and verify a host-update plan. This module never installs packages."""
import hashlib
from pathlib import Path
import re
import stat
import subprocess


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''): result.update(block)
    return result.hexdigest()


def parse_simulation(output):
    packages = []; removals = []; seen = set()
    pattern = re.compile(r'^Inst ([a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?) '
                         r'(?:\[([^\]\s]+)\] )?\(([^\s()]+) (.+) \[([a-z0-9-]+)\]\)'
                         r'(?: \[[^\]]*\])?$')
    for line in output.splitlines():
        if line.startswith('Remv '):
            removals.append(line.split()[1]); continue
        if not line.startswith('Inst '): continue
        match = pattern.fullmatch(line)
        if not match or match[1] in seen: raise ValueError('Ambiguous APT simulation transaction')
        seen.add(match[1])
        packages.append({'package': match[1], 'installed': match[2], 'candidate': match[3],
                         'origin': match[4], 'architecture': match[5]})
    if removals: raise ValueError('Package removal requires a separate review')
    if not packages: raise ValueError('No update transactions found')
    return packages


def deb822(text):
    result = []; row = {}; last = None
    for line in text.splitlines() + ['']:
        if not line:
            if row: result.append(row)
            row = {}; last = None
        elif line[0].isspace():
            if last is None: raise ValueError('Invalid package metadata continuation')
            row[last] += '\n' + line[1:]
        else:
            key, sep, value = line.partition(':')
            if not sep or key in row: raise ValueError('Invalid package metadata field')
            row[key] = value.strip(); last = key
    return result


def metadata(output, package, version, architecture):
    matches = [r for r in deb822(output) if r.get('Package') == package.split(':')[0]
               and r.get('Version') == version and r.get('Architecture') == architecture]
    identities = {(r.get('SHA256'), r.get('Size'), r.get('Filename'), r.get('Installed-Size')) for r in matches}
    if len(identities) != 1: raise ValueError('Missing or ambiguous authenticated package metadata')
    digest, size, filename, installed = identities.pop()
    if not digest or not re.fullmatch('[a-f0-9]{64}', digest): raise ValueError('Missing package SHA-256')
    if not size or not size.isdigit() or not installed or not installed.isdigit():
        raise ValueError('Missing package size')
    if not filename or Path(filename).is_absolute() or '..' in Path(filename).parts:
        raise ValueError('Invalid package repository path')
    return {'package': package, 'version': version, 'architecture': architecture,
            'sha256': digest, 'size_bytes': int(size), 'installed_kib': int(installed),
            'repository_filename': filename}


def verify_deb(path, record, *, run=subprocess.run):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError('Symlink in package cache')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != record['size_bytes'] or sha(path) != record['sha256']:
        raise ValueError('Downloaded package checksum or size mismatch')
    result = run(['dpkg-deb', '--field', str(path)], capture_output=True, text=True, check=True)
    rows = deb822(result.stdout)
    if len(rows) != 1 or any(rows[0].get(k) != value for k, value in (
        ('Package', record['package'].split(':')[0]), ('Version', record['version']), ('Architecture', record['architecture']))):
        raise ValueError('Downloaded package identity mismatch')


def hooks_are_empty(dump):
    import shlex
    for line in dump.splitlines():
        key = line.split(' ', 1)[0]
        if any(part in key for part in ('Post-Invoke', 'Pre-Invoke', 'Pre-Install-Pkgs')):
            fields = shlex.split(line.rstrip(';'))
            if len(fields) != 2 or fields[1]: return False
    return True
