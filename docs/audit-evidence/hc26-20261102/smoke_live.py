"""Execute candidate functions inside the live poller; only HA GET, no publish."""
import json
import sys
import time
import requests

namespace = {'__name__': 'hc26_candidate'}
exec(compile(sys.stdin.read(), '<HC-26 candidate>', 'exec'), namespace)
class Session(requests.Session):
    def __init__(self):
        super().__init__(); self.get_count = 0
    def get(self, *args, **kwargs):
        self.get_count += 1
        return super().get(*args, **kwargs)
with Session() as session:
    session.headers.update({'Authorization':'Bearer '+namespace['HA_TOKEN']})
    mapping = namespace['load_entity_map']()
    started = time.monotonic()
    payload = namespace['poll_payload'](session, mapping)
    result = dict(ok=session.get_count==1 and payload['entity_count']>0,
        get_count=session.get_count, elapsed_seconds=round(time.monotonic()-started,6),
        configured_metrics=len(mapping), published_metric_count=payload['entity_count'],
        per_metric_age_fields=sum('ha_state_age_seconds' in m and 'observed_at' in m for m in payload['meta'].values()),
        valid_age_values=sum(m['ha_state_age_seconds'] is not None for m in payload['meta'].values()),
        original_last_updated_fields=sum('last_updated' in m for m in payload['meta'].values()),
        credentials_exported=False, raw_states_saved=False, mqtt_publish_commands=0, ha_mutation_commands=0)
    print('HC26_SMOKE='+json.dumps(result))
    assert result['ok']
