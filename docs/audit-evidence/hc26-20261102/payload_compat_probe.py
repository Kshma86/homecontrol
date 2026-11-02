"""Compare the original main loop's MQTT fields with the new pure builder."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, '/src/apps/ha-growatt-poller')
import ha_growatt_poller as module
original = ast.parse(Path('/evidence/original/apps/ha-growatt-poller/ha_growatt_poller.py').read_text())
main = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
loop = next(n for n in ast.walk(main) if isinstance(n, ast.For))
now = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)
def state(entity, value='42'):
    return dict(entity_id=entity, state=value, attributes={'unit_of_measurement':'W', 'friendly_name':'Fixture'},
                last_updated='2026-11-02T14:00:00+00:00')
scenarios = [
    (module.DEFAULT_ENTITY_MAP, {entity:state(entity, str(n)) for n, entity in enumerate(module.DEFAULT_ENTITY_MAP.values())}),
    ({'good':'sensor.a','missing':'sensor.b','unknown':'sensor.c'}, {'sensor.a':state('sensor.a'), 'sensor.c':state('sensor.c','unknown')}),
    ({'bad':'sensor.a'}, {'sensor.a':state('sensor.a','unavailable')}),
    ({'first':'sensor.a','alias':'sensor.a'}, {'sensor.a':state('sensor.a')}),
]
results = []
with patch.object(module.socket, 'socket', side_effect=AssertionError('No external I/O')):
    for mapping, states in scenarios:
        old = dict(source='home_assistant', sample_time=now.isoformat())
        context = dict(entity_map=mapping, ha_get_state=lambda session, entity: states.get(entity), session=None,
                       coerce_state=module.coerce_state, payload=old, meta={}, ok_count=0)
        exec(compile(ast.Module(body=[loop], type_ignores=[]), '<original HC26 main loop>', 'exec'), context)
        old.update(entity_count=context['ok_count'], meta=context['meta'])
        current = module.build_payload(states, mapping, observed_at=now)
        projected = deepcopy(current)
        for metadata in projected['meta'].values():
            assert set(metadata)-set(old['meta'][next(k for k in old['meta'] if old['meta'][k]['entity_id']==metadata['entity_id'])]) == {'observed_at','ha_state_age_seconds'}
            metadata.pop('observed_at'); metadata.pop('ha_state_age_seconds')
        assert projected == old
        results.append(dict(configured_metrics=len(mapping), published_metrics=current['entity_count'],
                            original_fields_exactly_preserved=True, additive_metadata=['observed_at','ha_state_age_seconds']))
    print(json.dumps(dict(ok=True, scenarios=results, source='Original main for-loop AST, synthetic snapshot, fixed observation time', external_io=False)))
