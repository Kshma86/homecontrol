"""In-container test selection. Exclusions belong to explicit other profiles."""
import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT/'infra/backend'
OWNERSHIP = {
    'tests.test_access_release.AccessReleaseTest.test_cold_restore_fixes_actual_old_broker_mount_without_changing_other_releases',
    'tests.test_access_release.AccessReleaseTest.test_root_writer_leaves_state_and_lock_accessible_to_nonroot_api',
}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=('unit', 'ownership', 'postgres', 'deployed', 'mdns', 'growatt'))
    parser.add_argument('--module', help='One PostgreSQL module in its own disposable DB cluster')
    args = parser.parse_args()
    sys.path.insert(0, str(BACKEND))
    loader = unittest.TestLoader()
    if args.profile == 'mdns':
        sys.path.insert(0, str(ROOT/'infra/mdns'))
        suite = loader.discover(str(ROOT/'infra/mdns/tests'))
    elif args.profile == 'growatt':
        sys.path.insert(0, str(ROOT/'apps/ha-growatt-poller'))
        suite = loader.discover(str(ROOT/'apps/ha-growatt-poller/tests'))
    elif args.profile == 'ownership':
        suite = loader.loadTestsFromNames(sorted(OWNERSHIP))
    elif args.profile == 'postgres':
        if not args.module or not args.module.startswith('tests.test_') or not args.module.endswith('_postgres'):
            parser.error('postgres requires an explicit test module')
        suite = loader.loadTestsFromName(args.module)
    elif args.profile == 'deployed':
        suite = loader.loadTestsFromName('tests.test_deployment_policy')
    else:
        discovered = loader.discover(str(BACKEND/'tests'), top_level_dir=str(BACKEND))
        suite = unittest.TestSuite(t for t in flatten(discovered)
            if t.id() not in OWNERSHIP and not t.__class__.__module__.endswith('_postgres'))
    collected = list(flatten(suite))
    # unittest also collects TestCase classes imported by another test module.
    # Keep each canonical test ID once and report the discovery duplicates.
    unique = {test.id(): test for test in collected}
    suite = unittest.TestSuite(unique.values())
    ids = list(unique)
    if not ids:
        raise ValueError('Empty test selection')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'profile': args.profile, 'module': args.module, 'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'duplicate_imports_removed': len(collected)-len(ids),
        'test_ids': ids}))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
