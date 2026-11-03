"""Exercise the acceptance adapter with a transient user timer, never HC units."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
import uuid


def main():
    spec = importlib.util.spec_from_file_location('timer_settle_native_probe', Path(__file__).with_name('timer_settle.py'))
    adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
    name = 'hc-audit-r22-timer-probe-' + uuid.uuid4().hex[:10]
    timer, service = name + '.timer', name + '.service'
    adapter.TIMER, adapter.SERVICE = timer, service
    adapter.MISSING = 'Scheduled timer has no next trigger: ' + timer
    observations = []
    def call(args, **kwargs):
        return subprocess.run([args[0], '--user', *args[1:]], check=True, capture_output=True, timeout=10)
    core = SimpleNamespace(call=call)
    def check(context, plan, **kwargs):
        trigger = adapter.properties(context, timer, ('NextElapseUSecRealtime', 'NextElapseUSecMonotonic'))
        timer_state = adapter.properties(context, timer, ('ActiveState', 'SubState'))
        health = adapter.properties(context, service, ('ActiveState', 'SubState', 'Result', 'ExecMainStatus'))
        row = {'timer': {**timer_state, **trigger}, 'service': health}
        if not observations or row != observations[-1]: observations.append(row)
        if not any(v not in ('', '0', 'infinity', 'n/a') for v in trigger.values()):
            raise ValueError(adapter.MISSING)
        return {'timers': {timer: {'next_trigger': trigger}}}
    try:
        subprocess.run(['systemd-run', '--user', '--unit=' + name, '--on-active=1s',
            '--on-unit-inactive=3s', '--timer-property=AccuracySec=1ms', '--property=Type=oneshot',
            '--property=TimeoutStartSec=10s', '/bin/sleep', '3'], check=True, capture_output=True, timeout=10)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if adapter.properties(core, timer, ('SubState',)).get('SubState') == 'running': break
            time.sleep(.05)
        else: raise RuntimeError('Transient timer did not run')
        result = adapter.check(core, check, {}, timeout=10)
        proof = {'ok': True, 'scope': 'transient_user', 'production_units_modified': False,
                 'observations': observations, 'acceptance': result['health_service_acceptance'],
                 'test_scope': 'Real systemd wait adapter; complete frozen checks covered separately by integration fixtures.'}
    finally:
        subprocess.run(['systemctl', '--user', 'stop', timer, service], capture_output=True, timeout=10)
        subprocess.run(['systemctl', '--user', 'reset-failed', timer, service], capture_output=True, timeout=10)
    print(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__': main()
