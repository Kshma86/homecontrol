"""Check current scheduled units against the frozen generator, without installing."""
import hashlib
import importlib.util
from pathlib import Path


def schedule_plan(core):
    path = core.KIT / 'source/scripts/install_backup_f6.py'
    spec = importlib.util.spec_from_file_location('audit_frozen_schedule_generator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # apply=False returns before root checks, locks, writes or systemctl calls.
    # Read current settings; f6-installed.json describes an earlier installation.
    return module.install(apply=False, root=core.BASE / 'backups', restore_host=True)


def check_schedules(core, plan, *, release_units=True):
    if plan.get('scope') != 'system' or plan.get('applied') is not False:
        raise ValueError('Expected a read-only system schedule plan')
    enabled = plan['enabled']
    timers = {n: wanted for n, wanted in enabled.items() if n.endswith('.timer')}
    if len(timers) != 5 or not all(wanted is True for wanted in timers.values()):
        raise ValueError('Expected five configured router backup timers')
    expected = dict(plan['units'])
    if release_units:
        for name, text in core.platform().units(core.KIT / 'source').items():
            digest = hashlib.sha256(text.encode()).hexdigest()
            if name in expected and expected[name] != digest:
                raise ValueError('Conflicting expected unit: ' + name)
            expected[name] = digest
    for name, wanted in expected.items():
        target = core.UNIT_ROOT / name
        core.platform().no_symlinks(target)
        if core.digest(target) != wanted:
            raise ValueError('Backup unit changed: ' + name)
    for name, wanted in enabled.items():
        actual = core.call(['systemctl', 'is-enabled', name], allowed=(0, 1, 3, 4)).stdout
        if isinstance(actual, bytes):
            actual = actual.decode()
        if (actual.strip() == 'enabled') != bool(wanted):
            raise ValueError('Scheduled unit enablement differs: ' + name)
        if core.active(name) != bool(wanted):
            raise ValueError('Scheduled unit active state differs: ' + name)
    result = {}
    for name in timers:
        output = core.call(['systemctl', 'show', name,
                           '--property=NextElapseUSecRealtime,NextElapseUSecMonotonic',
                           '--no-pager']).stdout
        if isinstance(output, bytes):
            output = output.decode()
        triggers = dict(line.split('=', 1) for line in output.strip().splitlines() if '=' in line)
        if not any(value.strip() not in ('', '0', 'infinity', 'n/a') for value in triggers.values()):
            raise ValueError('Scheduled timer has no next trigger: ' + name)
        result[name] = {'active': True, 'enabled': True, 'next_trigger': triggers}
    return {'timers': result, 'unit_sha256': expected,
            'settings_source': 'current backup_settings.json through frozen schedule generator',
            'read_only': True}
