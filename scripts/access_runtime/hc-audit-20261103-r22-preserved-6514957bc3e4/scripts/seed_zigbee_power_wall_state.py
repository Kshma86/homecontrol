import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from app import db_conn


STATE_PATH = Path("/srv/docker/homecontrol/infra/zigbee2mqtt/data/state.json")
KEY_MAP = {
    "state": "switch_state",
    "power": "power",
    "current": "current",
    "energy": "energy_kwh",
    "voltage": "mains_voltage_v",
    "linkquality": "linkquality",
}


def is_power_plug(payload):
    if not isinstance(payload, dict):
        return False
    return "state" in payload and bool(set(payload) & {"power", "current", "energy", "voltage"})


def main():
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    ext_ids = [ext_id for ext_id, payload in state.items() if is_power_plug(payload)]
    presence_rows = []
    state_rows = []

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select e.id, d.ext_id
                from hc.entity e
                join hc.device d on d.id = e.device_id
                where d.platform = 'zigbee'
                  and d.ext_id = any(%s)
                """,
                (ext_ids,),
            )
            entity_by_ext = {ext_id: entity_id for entity_id, ext_id in cur.fetchall()}

            for ext_id, entity_id in entity_by_ext.items():
                payload = state.get(ext_id, {})
                presence_rows.append((entity_id,))
                for raw_key, metric_key in KEY_MAP.items():
                    if raw_key not in payload:
                        continue
                    value = payload[raw_key]
                    meta = json.dumps({"source": "zigbee2mqtt-state-seed", "raw_key": raw_key})
                    if metric_key == "switch_state":
                        state_rows.append((entity_id, metric_key, None, str(value).upper() == "ON", None, None, meta))
                    elif isinstance(value, (int, float)):
                        state_rows.append((entity_id, metric_key, float(value), None, None, None, meta))

            cur.executemany(
                """
                insert into hc.entity_presence (entity_id, last_seen_ts, status, updated_at)
                values (%s, now(), 'online', now())
                on conflict (entity_id) do update set
                  last_seen_ts = excluded.last_seen_ts,
                  status = excluded.status,
                  updated_at = now()
                """,
                presence_rows,
            )
            cur.executemany(
                """
                insert into hc.entity_state (entity_id, key, ts, v_num, v_bool, v_text, v_json, meta)
                values (%s, %s, now(), %s, %s, %s, %s, %s::jsonb)
                on conflict (entity_id, key) do update set
                  ts = excluded.ts,
                  v_num = excluded.v_num,
                  v_bool = excluded.v_bool,
                  v_text = excluded.v_text,
                  v_json = excluded.v_json,
                  meta = excluded.meta
                """,
                state_rows,
            )

    print(f"seeded {len(entity_by_ext)} devices, {len(state_rows)} state rows")


if __name__ == "__main__":
    main()
