"""Wait for the bounded health oneshot, then require every frozen schedule check."""
import time

TIMER = 'homecontrol-post-boot-health.timer'
SERVICE = 'homecontrol-post-boot-health.service'
MISSING = 'Scheduled timer has no next trigger: ' + TIMER


def properties(core, unit, names):
    output = core.call(['systemctl', 'show', unit, '--property=' + ','.join(names),
                        '--no-pager'], timeout=10).stdout
    if isinstance(output, bytes): output = output.decode()
    return dict(line.split('=', 1) for line in output.strip().splitlines() if '=' in line)


def check(core, frozen_check, plan, *, timeout=210, clock=time.monotonic,
          sleep=time.sleep, **kwargs):
    started = clock(); deadline = started + timeout; idle_since = None; waited = False
    announced = False
    while True:
        # Do not bypass or weaken any sealed byte, enablement or trigger check.
        # Only the exact health timer's transient missing trigger is retryable.
        try:
            result = frozen_check(core, plan, **kwargs)
        except ValueError as error:
            if str(error) != MISSING: raise
            result = None
        timer = properties(core, TIMER, ('LoadState', 'ActiveState', 'SubState', 'Unit'))
        service = properties(core, SERVICE, ('LoadState', 'ActiveState', 'SubState',
                                             'Result', 'ExecMainStatus', 'Type'))
        if (timer.get('LoadState') != 'loaded' or timer.get('ActiveState') != 'active'
                or timer.get('Unit') != SERVICE or timer.get('SubState') not in ('waiting', 'running')):
            raise ValueError('Health timer is not ready for schedule acceptance')
        if (service.get('LoadState') != 'loaded' or service.get('Type') != 'oneshot'
                or service.get('Result') != 'success'):
            raise ValueError('Health service failed during schedule acceptance')
        busy = (service.get('ActiveState'), service.get('SubState')) in (
            ('activating', 'start'), ('activating', 'start-pre'), ('activating', 'start-post'),
            ('active', 'running'), ('deactivating', 'stop'), ('deactivating', 'stop-post'))
        if not busy:
            if (service.get('ActiveState'), service.get('SubState'), service.get('ExecMainStatus')) != ('inactive', 'dead', '0'):
                raise ValueError('Health service did not finish successfully')
            if result is not None and timer.get('SubState') == 'waiting':
                result['health_service_acceptance'] = {
                    'result': 'success', 'exit_status': 0, 'timer_state': 'waiting',
                    'waited_for_completion': waited, 'wait_seconds': round(clock() - started, 3),
                    'all_frozen_schedule_checks_passed': True,
                }
                return result
            if idle_since is None: idle_since = clock()
            if clock() - idle_since >= 5:
                raise ValueError(MISSING)
        else:
            idle_since = None
            if timer.get('SubState') != 'running':
                raise ValueError('Health timer and service state disagree')
        if clock() >= deadline:
            raise ValueError('Health service did not settle before schedule deadline')
        if not announced:
            print('A post-boot health futás befejezésére várunk; utána az összes eredeti timer-ellenőrzés újrafut.', flush=True)
            announced = True
        waited = True
        sleep(min(1, max(0, deadline - clock())))


def install(core, module):
    frozen = module.check_schedules
    def checked(context, plan, **kwargs):
        return check(context, frozen, plan, **kwargs)
    module.check_schedules = checked
