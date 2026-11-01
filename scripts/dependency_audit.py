"""Offline PyPI/OSV comparison. No inventory is sent over the network.

Inputs: an inventory mapping component -> [[distribution, version], ...] and
the complete public PyPI OSV ZIP. Unknown ranges are explicit review items.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import zipfile
from packaging.version import InvalidVersion, Version


def normalize(value):
    return re.sub(r'[-_.]+', '-', value).lower()


def affected(entry, raw_version):
    if raw_version in entry.get('versions', []):
        return True
    version = Version(raw_version)
    unknown = False
    for block in entry.get('ranges', []):
        if block['type'] not in ('ECOSYSTEM', 'SEMVER'):
            unknown = True
            continue
        active = False
        for event in block['events']:
            if 'introduced' in event:
                active = event['introduced'] == '0' or version >= Version(event['introduced'])
            else:
                key = next((k for k in ('fixed', 'last_affected', 'limit') if k in event), None)
                if key is None:
                    unknown = True
                    continue
                end = Version(event[key])
                if active and (version < end or key == 'last_affected' and version == end):
                    return True
                active = False
        if active:
            return True
    return None if unknown else False


def scan(inventory, catalog, *, cutoff):
    packages = {}
    for component, rows in inventory.items():
        for name, version in rows:
            packages.setdefault(normalize(name), {}).setdefault(version, []).append(component)
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
                if package.get('ecosystem') != 'PyPI':
                    continue
                for version, components in packages.get(normalize(package.get('name', '')), {}).items():
                    try:
                        hit = affected(entry, version)
                    except (InvalidVersion, KeyError, TypeError):
                        hit = None
                    row = {'id': record['id'], 'aliases': record.get('aliases', []),
                           'package': normalize(package['name']), 'version': version,
                           'components': components, 'summary': record.get('summary', ''),
                           'ranges': entry.get('ranges', []),
                           'references': record.get('references', [])}
                    if hit:
                        matches.append(row)
                    elif hit is None:
                        unknown.append(row)
    return {'cutoff': cutoff, 'catalog_records': records,
            'matches': matches, 'unknown': unknown, 'private_inventory_uploaded': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cutoff', default=date.today().isoformat())
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    result = scan(inventory.get('python', inventory), args.catalog, cutoff=args.cutoff)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'matched_records': len(result['matches']), 'unknown': len(result['unknown'])}))


if __name__ == '__main__':
    main()
