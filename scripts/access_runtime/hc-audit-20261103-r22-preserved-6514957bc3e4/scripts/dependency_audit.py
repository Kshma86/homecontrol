"""Offline PyPI/npm OSV comparison. No inventory is sent over the network.

Inputs: an inventory mapping component -> [[distribution, version], ...] and
the complete public PyPI OSV ZIP. Unknown ranges are explicit review items.
"""
import argparse
from datetime import date
from functools import total_ordering
import json
from pathlib import Path
import re
import zipfile
from packaging.version import InvalidVersion, Version


def normalize(value):
    return re.sub(r'[-_.]+', '-', value).lower()


@total_ordering
class SemVer:
    """OSV SEMVER event ordering, including prereleases and build metadata."""
    def __init__(self, raw):
        match = re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
                             r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
                             r'(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?', raw)
        if not match:
            raise ValueError('Invalid semantic version')
        self.release = tuple(int(match[i]) for i in (1, 2, 3))
        self.pre = tuple(match[4].split('.')) if match[4] else ()
        if any(x.isdigit() and len(x) > 1 and x[0] == '0' for x in self.pre):
            raise ValueError('Leading zero in prerelease')

    def __eq__(self, other):
        return (self.release, self.pre) == (other.release, other.pre)

    def __lt__(self, other):
        if self.release != other.release:
            return self.release < other.release
        if not self.pre or not other.pre:
            return bool(self.pre) and not other.pre
        for left, right in zip(self.pre, other.pre):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.pre) < len(other.pre)


def affected(entry, raw_version, *, ecosystem='PyPI'):
    if raw_version in entry.get('versions', []):
        return True
    parse = SemVer if ecosystem == 'npm' else Version
    version = parse(raw_version)
    unknown = not (entry.get('ranges') or entry.get('versions'))
    for block in entry.get('ranges', []):
        if block['type'] not in ('ECOSYSTEM', 'SEMVER'):
            unknown = True
            continue
        active = False
        for event in block['events']:
            if 'introduced' in event:
                active = event['introduced'] == '0' or version >= parse(event['introduced'])
            else:
                key = next((k for k in ('fixed', 'last_affected', 'limit') if k in event), None)
                if key is None:
                    unknown = True
                    continue
                end = parse(event[key])
                if active and (version < end or key == 'last_affected' and version == end):
                    return True
                active = False
        if active:
            return True
    return None if unknown else False


def npm_inventory(lock):
    if lock.get('lockfileVersion') not in (2, 3) or not isinstance(lock.get('packages'), dict):
        raise ValueError('A complete npm v2/v3 package lock is required')
    rows = set()
    for path, item in lock['packages'].items():
        if not path or item.get('link'):
            continue
        name = item.get('name') or path.rsplit('node_modules/', 1)[-1]
        if not name or not item.get('version'):
            raise ValueError('Incomplete locked package')
        rows.add((name, item['version']))
    return {'frontend_build': sorted(rows)}


def advisory_groups(rows):
    groups = []
    for row in rows:
        ids = {row['id'], *row.get('aliases', [])}
        overlaps = [group for group in groups if group & ids]
        for group in overlaps:
            ids.update(group)
            groups.remove(group)
        groups.append(ids)
    return sorted(sorted(group) for group in groups)


def scan(inventory, catalog, *, cutoff, ecosystem='PyPI'):
    if ecosystem not in ('PyPI', 'npm'):
        raise ValueError('Unsupported ecosystem')
    normalize_name = normalize if ecosystem == 'PyPI' else lambda value: value
    packages = {}
    for component, rows in inventory.items():
        for name, version in rows:
            packages.setdefault(normalize_name(name), {}).setdefault(version, []).append(component)
    matches, unknown = [], []
    records = 0
    with zipfile.ZipFile(catalog) as archive:
        for name in archive.namelist():
            if not name.endswith('.json'):
                continue
            record = json.loads(archive.read(name))
            if record.get('withdrawn') or record.get('published', '')[:10] > cutoff:
                continue
            records += 1
            for entry in record.get('affected', []):
                package = entry.get('package', {})
                if package.get('ecosystem') != ecosystem:
                    continue
                for version, components in packages.get(normalize_name(package.get('name', '')), {}).items():
                    try:
                        hit = affected(entry, version, ecosystem=ecosystem)
                    except (ValueError, KeyError, TypeError):
                        hit = None
                    row = {'id': record['id'], 'aliases': record.get('aliases', []),
                           'package': normalize_name(package['name']), 'version': version,
                           'components': components, 'summary': record.get('summary', ''),
                           'ranges': entry.get('ranges', []),
                           'references': record.get('references', [])}
                    if hit:
                        matches.append(row)
                    elif hit is None:
                        unknown.append(row)
    return {'cutoff': cutoff, 'ecosystem': ecosystem, 'catalog_records': records,
            'package_version_pairs': sum(len(versions) for versions in packages.values()),
            'matches': matches, 'unknown': unknown,
            'distinct_advisory_groups': advisory_groups(matches),
            'private_inventory_uploaded': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cutoff', default=date.today().isoformat())
    parser.add_argument('--ecosystem', choices=('PyPI', 'npm'), default='PyPI')
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    inventory = npm_inventory(inventory) if args.ecosystem == 'npm' else inventory.get('python', inventory)
    result = scan(inventory, args.catalog, cutoff=args.cutoff, ecosystem=args.ecosystem)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'matched_records': len(result['matches']), 'unknown': len(result['unknown'])}))


if __name__ == '__main__':
    main()
