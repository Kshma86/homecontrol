"""Compare before/after V2 side effects with controlled time and fake physical I/O."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, '/src/infra/backend')

def forbidden(*args, **kwargs):
    raise AssertionError('HC-20 parity probe attempted external work')

def guard(event, args):
    if event in ('socket.connect', 'socket.connect_ex', 'socket.bind', 'subprocess.Popen', 'os.system', 'os.fork'):
        forbidden()
    if event == 'open':
        path, mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            forbidden()

sys.addaudithook(guard)
with patch.object(threading.Thread, 'start', side_effect=forbidden):
    from tests import test_irrigation_service as fixture
    from irrigation_service import IrrigationService as Current
    spec = importlib.util.spec_from_file_location('hc20_before', '/evidence/original/infra/backend/irrigation_service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    Before = module.IrrigationService
    def capture(cls, mode='navigator', minutes=7, confirmed=True, stop_status=None, stop=False):
        holder = fixture.IrrigationV2ScheduleRegressionTest()
        with patch.object(fixture, 'IrrigationService', cls):
            service = holder.service(mode=mode, final_duration=minutes, confirmed=confirmed)
        closes = []
        if stop:
            service.fetch_all = lambda *args: [dict(id=7, session_id=11 if stop_status else None,
                session_status=stop_status, requested_stop_at=holder.now)]
            service.stop_manual_session = lambda *args: (closes.append(args) or confirmed, 'fixture close', {})
            service.stop_v2_due_schedules()
        else:
            service.start_v2_scheduled_session(7)
        return dict(reservations=holder.reservations, opens=holder.opens, writes=holder.writes,
                    executions=holder.executions, decisions=holder.decisions, closes=closes,
                    recovery_blocked=service.session_recovery.blocked)
    scenarios = [dict(mode='navigator', minutes=7), dict(mode='pilot', minutes=30),
                 dict(mode='pilot', minutes=0), dict(mode='pilot', minutes=7, confirmed=False)]
    scenarios += [dict(stop=True, stop_status=status, confirmed=ok)
                  for status, ok in [('running', True), ('running', False), ('stop_failed', True),
                                     ('starting', True), ('stopped', True), ('auto_stopped', True),
                                     ('start_failed', True), (None, True)]]
    records = []
    for values in scenarios:
        previous = capture(Before, **values)
        current = capture(Current, **values)
        assert previous == current, values
        records.append(dict(scenario=values, exact_side_effect_parity=True, result=current))
    print('HC20_PARITY_JSON=' + json.dumps(dict(ok=True, scenarios=len(records),
        comparison='Exact fake-MQTT payloads, reservation inputs, SQL/parameters, execution/decision outputs and recovery state',
        external_work=False, results=records), default=lambda value: value.isoformat(), sort_keys=True))
