"""Download and seal the reviewed Jammy package plan, without installing anything."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path('/srv/docker/homecontrol')
ROOT = BASE / 'maintenance/host-update-20261103'
spec = importlib.util.spec_from_file_location('host_update_package_plan', Path(__file__).with_name('plan.py'))
plan = importlib.util.module_from_spec(spec); spec.loader.exec_module(plan)


def main():
    if os.geteuid() == 0: raise PermissionError('Preparation downloads run as the operator, not root')
    os.umask(0o077)
    if (ROOT / 'plan.json').exists(): raise ValueError('A prepared plan already exists; preserve it before refreshing')
    config = ROOT / 'apt/prepare.conf'
    env = {**os.environ, 'LC_ALL': 'C', 'LANG': 'C'}; env.pop('APT_CONFIG', None)
    def call(args, **kwargs):
        return subprocess.run(args, capture_output=True, text=True, check=True, env=env, timeout=300, **kwargs)
    before = plan.sha('/var/lib/dpkg/status')
    dump = call(['apt-config', '-c', str(config), 'dump']).stdout
    if not plan.hooks_are_empty(dump): raise ValueError('Preparation APT hooks are not empty')
    simulation = call(['apt-get', '-c', str(config), '--simulate', '--with-new-pkgs', 'upgrade'])
    (ROOT / 'evidence/apt-simulation.log').write_text(simulation.stdout + simulation.stderr)
    rows = plan.parse_simulation(simulation.stdout)
    for row in rows:
        output = call(['apt-cache', '-c', str(config), 'show', row['package'] + '=' + row['candidate']]).stdout
        row['catalog'] = plan.metadata(output, row['package'], row['candidate'], row['architecture'])
        (ROOT / 'evidence' / (row['package'].replace(':', '_') + '.metadata')).write_text(output)
    rollback = []
    for row in rows:
        if row['installed'] and row['package'] in ('docker-ce', 'docker-ce-cli', 'containerd.io',
                'docker-compose-plugin', 'docker-buildx-plugin', 'docker-ce-rootless-extras',
                'netplan.io', 'libnetplan0'):
            output = call(['apt-cache', '-c', str(config), 'show', row['package'] + '=' + row['installed']]).stdout
            rollback.append(plan.metadata(output, row['package'], row['installed'], row['architecture']))
    for group, records in (('upgrade', [r['catalog'] for r in rows]), ('rollback', rollback)):
        directory = ROOT / 'packages' / group
        with (ROOT / 'evidence' / (group + '-download.log')).open('a') as log:
            for index, record in enumerate(records):
                candidates = []
                for path in directory.glob('*.deb'):
                    if path.stat().st_size == record['size_bytes'] and plan.sha(path) == record['sha256']:
                        candidates.append(path)
                if not candidates:
                    result = call(['apt-get', '-c', str(config), 'download', record['package'] + '=' + record['version']], cwd=directory)
                    log.write(result.stdout + result.stderr); log.flush()
                    candidates = [p for p in directory.glob('*.deb') if p.stat().st_size == record['size_bytes'] and plan.sha(p) == record['sha256']]
                if len(candidates) != 1: raise ValueError('Expected exactly one matching downloaded package')
                plan.verify_deb(candidates[0], record)
                record['local_file'] = str(candidates[0].relative_to(ROOT))
                print(group + ': ' + str(index + 1) + '/' + str(len(records)) + ' ' + record['package'], flush=True)
    if plan.sha('/var/lib/dpkg/status') != before: raise ValueError('Host package state changed during preparation')
    result = {'prepared_at': datetime.now(timezone.utc).isoformat(), 'os_codename': 'jammy',
        'package_database_sha256': before, 'transactions': rows, 'rollback_packages': rollback,
        'upgrades': sum(r['installed'] is not None for r in rows), 'new_packages': sum(r['installed'] is None for r in rows),
        'removals': [], 'download_bytes': sum(r['catalog']['size_bytes'] for r in rows),
        'rollback_download_bytes': sum(r['size_bytes'] for r in rollback),
        'installed_size_upper_bound_bytes': sum(r['catalog']['installed_kib'] * 1024 for r in rows),
        'packages_installed': False, 'services_restarted': False, 'reboot_performed': False,
        'isolated_apt_catalog': True, 'signature_checks_disabled': False,
        'host_apt_hooks_disabled_for_metadata_download_only': True,
        'automatic_os_downgrade_supported': False,
        'prior_packages_are_recovery_material_not_a_tested_downgrade': True}
    (ROOT / 'plan.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:result[k] for k in ('upgrades','new_packages','download_bytes','rollback_download_bytes','packages_installed')},indent=2))


if __name__ == '__main__': main()
