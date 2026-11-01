"""Durable latch/history only; no DDL, business configuration or MQTT here."""


class CombustionStateStore:
    def __init__(self, fetch_one, execute_one):
        self.fetch_one, self.execute_one = fetch_one, execute_one

    def load(self):
        row = self.fetch_one('select * from hc.combustion_safety_runtime where singleton=true')
        if not row:
            raise RuntimeError('combustion runtime state missing; apply migration 058')
        return row

    def save(self, revision, state, *, acknowledge=False):
        row = self.execute_one('''
            update hc.combustion_safety_runtime
            set revision=revision+1, latched=%s, co_warning_active=%s,
                last_co=%s, last_co_sample_at=to_timestamp(%s), updated_at=now(),
                acknowledged_at=case when %s then now() else acknowledged_at end
            where singleton=true and revision=%s
            returning *
            ''', (state['latched'], state['co_warning_active'], state['last_co'],
                  state['last_co_sample_at'], acknowledge, revision))
        if not row:
            raise RuntimeError('combustion runtime revision changed; refusing stale state write')
        return row
