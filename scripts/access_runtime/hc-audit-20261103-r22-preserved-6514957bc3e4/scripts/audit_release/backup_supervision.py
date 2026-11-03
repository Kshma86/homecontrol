"""Bound acceptance backups to one transient systemd cgroup, including workers."""
from pathlib import Path
import subprocess

UNIT = 'homecontrol-r22-acceptance-backup.service'
RUNTIME_SECONDS = 11400
CLIENT_SECONDS = RUNTIME_SECONDS + 180


def command(args, *, unit=UNIT, user=False, runtime=RUNTIME_SECONDS, stop_seconds=90):
    return ['systemd-run', *(['--user'] if user else []), '--quiet', '--wait', '--pipe', '--collect',
            '--unit=' + unit, '--property=Type=exec', '--property=KillMode=mixed',
            '--property=RuntimeMaxSec=' + str(runtime), '--property=TimeoutStopSec=' + str(stop_seconds),
            '--setenv=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            '--setenv=DOCKER_HOST=unix:///var/run/docker.sock',
            '--setenv=HC_BACKUP_TIMEOUT_SECONDS=10800', *map(str, args)]


def supervised_call(original, args, **kwargs):
    # The runner has its own 10800 s timeout and graceful worker-group cleanup.
    # The enclosing service survives a broken client and bounds all descendants.
    state = original(['systemctl', 'show', UNIT, '--property=LoadState', '--value'], allowed=(0, 1, 4))
    loaded = state.stdout.decode().strip() if isinstance(state.stdout, bytes) else state.stdout.strip()
    if loaded != 'not-found':
        raise ValueError('Acceptance backup supervisor already exists; reconcile it first')
    kwargs['timeout'] = CLIENT_SECONDS
    try:
        return original(command(args), **kwargs)
    except BaseException:
        # SIGTERM goes to the runner first; systemd kills the entire cgroup after
        # its stop grace. No child is left running when rollback is attempted.
        original(['systemctl', 'stop', UNIT], allowed=(0, 5), timeout=120)
        raise


def install(core):
    original = core.call
    approved = {str(root / 'scripts/hostops/backup_runner.py') for root in (core.OLD_RUNTIME, core.RUNTIME)}

    def call(args, **kwargs):
        if (len(args) == 4 and Path(args[0]).name in ('python3', 'python')
                and str(args[1]) in approved and args[2] == '--mode'
                and args[3] in ('local', 'weekly')):
            print('Mentés systemd-felügyelettel; a worker legfeljebb 3 órát futhat, utána szabályos leállítás következik.', flush=True)
            return supervised_call(original, args, **kwargs)
        return original(args, **kwargs)

    core.call = call
    core.BUSY_UNITS = (*core.BUSY_UNITS, UNIT)
