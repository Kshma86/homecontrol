"""Durable window interlock shared by manual and scheduled HC commands."""
from runtime_schema_contract import check_runtime_schema
import json
import math
import threading
import time

SCHEMA = """
create table if not exists hc.climate_window_guard (
 id integer primary key check(id=1),
 open_delay_seconds integer not null default 60,
 close_delay_seconds integer not null default 60,
 desired jsonb not null default '{}',
 suspended boolean not null default false
);
insert into hc.climate_window_guard(id) values(1) on conflict do nothing;
"""


class ClimateWindowGuard:
    def __init__(self, fetch_all, fetch_one, execute_one, publish, live_state, extractor, radio, sync):
        self.fetch_all, self.fetch_one, self.execute_one = fetch_all, fetch_one, execute_one
        self.publish, self.live_state, self.extractor, self.radio, self.sync = publish, live_state, extractor, radio, sync
        self.lock = threading.RLock()
        self.ready = False
        self.open_since = self.clear_since = None
        self.last_action = 0

    def config(self):
        if not self.ready:
            check_runtime_schema(self.execute_one, "climate_window")
            self.ready = True
        config = self.fetch_one('select * from hc.climate_window_guard where id=1')
        if not config:
            raise RuntimeError('Missing climate window configuration; run migrate_hc39.py --apply explicitly.')
        return config

    def save_config(self, data):
        with self.lock:
            current = self.config()
            values = []
            for key in ('open_delay_seconds', 'close_delay_seconds'):
                value = data.get(key, current[key])
                if isinstance(value, bool) or not str(value).isdigit() or not 0 <= int(value) <= 3600:
                    raise ValueError('A késleltetés egész szám legyen 0 és 3600 másodperc között.')
                values.append(int(value))
            self.execute_one('update hc.climate_window_guard set open_delay_seconds=%s, close_delay_seconds=%s where id=1 returning id', tuple(values))
            return self.status()

    def status(self, now=None):
        with self.lock:
            now = time.monotonic() if now is None else now
            cfg = self.config()
            fan_active = bool(self.extractor().get('fan_active'))
            rows = self.fetch_all("""select e.id,e.name,coalesce(nullif(p.opening_label,''),e.name) label,
                d.ext_id,p.extractor_air_role,s.v_bool contact from hc.opening_sensor_policy p
                join hc.entity e on e.id=p.entity_id join hc.device d on d.id=e.device_id
                left join hc.entity_state s on s.entity_id=e.id and s.key='contact'
                where p.climate_relevant=true and e.is_active=true and d.is_active=true""")
            blockers, exempt = [], []
            for row in rows:
                unknown = row['contact'] is None or self.radio(row['ext_id']).get('radio_online') is False
                if fan_active and row.get('extractor_air_role') == 'primary' and row['contact'] is False and not unknown:
                    exempt.append(row['label'])
                elif row['contact'] is not True or unknown:
                    blockers.append({'id': row['id'], 'label': row['label'], 'unknown': unknown})
            if blockers:
                if self.open_since is None:
                    self.open_since = now
                self.clear_since = None
            else:
                if self.clear_since is None:
                    self.clear_since = now
                self.open_since = None
            remaining = max(0, cfg['close_delay_seconds'] - (now - self.clear_since)) if self.clear_since is not None and cfg['suspended'] else 0
            blocked = bool(blockers) or remaining > 0
            stop_remaining = max(0, cfg['open_delay_seconds'] - (now - self.open_since)) if blockers else 0
            return {**cfg, 'blocked': blocked, 'blockers': blockers, 'exempt': exempt,
                    'open_remaining_seconds': math.ceil(stop_remaining), 'close_remaining_seconds': math.ceil(remaining)}

    def command(self, topic, payload, qos=0, retain=False):
        with self.lock:
            if payload.get('shadow_only') or payload.get('refresh'):
                return self.publish(topic, payload, qos=qos, retain=retain)
            status = self.status()
            desired = dict(status['desired'])
            desired.update({k: v for k, v in payload.items() if k != 'shadow_only'})
            if payload.get('power') == 'on' and status['blocked']:
                self.execute_one('update hc.climate_window_guard set desired=%s::jsonb,suspended=true where id=1 returning id', (json.dumps(desired),))
                return False, 'Ablak miatt tiltva; az indítás az ablakzárási késleltetés után teljesül.'
            ok, message = self.publish(topic, payload, qos=qos, retain=retain)
            if ok:
                self.execute_one('update hc.climate_window_guard set desired=%s::jsonb,suspended=%s where id=1 returning id', (json.dumps(desired), status['suspended'] and payload.get('power') != 'off'))
            return ok, message

    def tick(self, topic):
        with self.lock:
            status = self.status()
            live = self.live_state() or {}
            if status['blockers'] and status['open_remaining_seconds'] == 0 and live.get('power') == 'on':
                if time.monotonic() - self.last_action < 10:
                    return
                desired = {k: live[k] for k in ('power','mode','target_temperature','fan_speed','light') if live.get(k) is not None}
                # Retain a newer deferred scheduler command while retrying OFF.
                if not status['suspended']:
                    self.execute_one('update hc.climate_window_guard set desired=%s::jsonb,suspended=true where id=1 returning id', (json.dumps(desired),))
                ok, _ = self.publish(topic, {'power': 'off'})
                self.last_action = time.monotonic()
                if ok:
                    self.sync('off')
            elif not status['blocked'] and status['suspended']:
                desired = status['desired']
                ok, _ = self.publish(topic, desired) if desired.get('power') == 'on' else (True, '')
                if ok:
                    self.execute_one('update hc.climate_window_guard set suspended=false where id=1 returning id')
                    if desired.get('power') == 'on':
                        self.sync('on')
