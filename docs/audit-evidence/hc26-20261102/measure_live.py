"""Run inside the poller with its existing credentials; emit aggregate GET metrics only."""
import json
import signal
import statistics
import time

import ha_growatt_poller as poller
import requests


def expired(*args):
    raise TimeoutError('read-only measurement budget expired')

signal.signal(signal.SIGALRM, expired)
signal.setitimer(signal.ITIMER_REAL, 20)
entity_map = poller.load_entity_map()
ids = set(entity_map.values())
session = requests.Session()
session.headers.update({'Authorization': 'Bearer ' + poller.HA_TOKEN})
records = []
try:
    for number in range(3):
        record = {}
        for kind in (('individual', 'batch') if number % 2 == 0 else ('batch', 'individual')):
            started = time.monotonic()
            size = count = matched = 0
            paths = ['/api/states/' + entity for entity in entity_map.values()] if kind == 'individual' else ['/api/states']
            for path in paths:
                with session.get(poller.HA_BASE_URL + path, timeout=(3, 5), allow_redirects=False) as response:
                    response.raise_for_status()
                    raw = response.content
                    size += len(raw); count += 1
                    value = response.json()
                    states = value if kind == 'batch' else [value]
                    if not isinstance(states, list):
                        raise ValueError('Expected state list')
                    if kind == 'batch':
                        record['ha_state_count'] = len(states)
                    matched += sum(isinstance(s, dict) and s.get('entity_id') in ids for s in states)
            record[kind] = dict(seconds=round(time.monotonic()-started, 6), response_bytes=size,
                                get_requests=count, configured_entities_found=matched)
        records.append(record)
    result = dict(ok=True, configured_metric_count=len(entity_map), configured_entity_count=len(ids),
                  rounds=records, individual_median_seconds=statistics.median(r['individual']['seconds'] for r in records),
                  batch_median_seconds=statistics.median(r['batch']['seconds'] for r in records),
                  method='GET /api/states and GET /api/states/<configured id>; alternating order; one persistent session',
                  credentials_exported=False, raw_states_saved=False, mqtt_publish_commands=0, ha_mutation_commands=0)
    print(json.dumps(result))
finally:
    session.close()
    signal.setitimer(signal.ITIMER_REAL, 0)
