import threading
from typing import Any, Callable, Dict


class AdminService:
    CONTEXT_SECTIONS = ("power_wall", "tuya", "irrigation", "home_statistics")

    def __init__(
        self,
        db_conn: Callable[..., Any],
        dict_row: Any,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        execute_one: Callable[..., Any],
        execute_sql: Callable[..., Any],
        normalize_text: Callable[..., str],
        json_ready: Callable[[Any], Any],
        api_cache_get: Callable[[str], Any],
        api_cache_set: Callable[[str, Any, float], Any],
        api_cache_delete_prefix: Callable[[str], Any],
        invalidate_context: Callable[..., Any],
        context_meta: Callable[..., Dict[str, Any]],
        absolute_humidity_g_m3: Callable[[Any, Any], Any],
        irrigation_context: Callable[[], Any],
        scheduler_state: Callable[[], Any],
    ):
        self.db_conn = db_conn
        self.dict_row = dict_row
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.execute_sql = execute_sql
        self.normalize_text = normalize_text
        self.json_ready = json_ready
        self.api_cache_get = api_cache_get
        self.api_cache_set = api_cache_set
        self.api_cache_delete_prefix = api_cache_delete_prefix
        self.invalidate_context = invalidate_context
        self.context_meta = context_meta
        self.absolute_humidity_g_m3 = absolute_humidity_g_m3
        self.irrigation_context = irrigation_context
        self.scheduler_state = scheduler_state
        self._notes_schema_ready = False
        self._notes_schema_lock = threading.Lock()
        self._opening_schema_ready = False
        self._opening_schema_lock = threading.Lock()

    def ensure_opening_schema(self):
        if self._opening_schema_ready:
            return
        with self._opening_schema_lock:
            if self._opening_schema_ready:
                return
            self.execute_sql(
                """
                create table if not exists hc.opening_sensor_policy (
                  entity_id bigint primary key references hc.entity(id) on delete cascade,
                  opening_type text not null default 'window' check (opening_type in ('window', 'door')),
                  room_position integer,
                  opening_label text,
                  has_mosquito_net boolean not null default false,
                  rain_alert_enabled boolean not null default false,
                  updated_at timestamptz not null default now()
                );

                alter table hc.opening_sensor_policy
                  add column if not exists room_position integer;
                alter table hc.opening_sensor_policy
                  add column if not exists opening_label text;
                alter table hc.opening_sensor_policy
                  add column if not exists has_mosquito_net boolean not null default false;
                alter table hc.opening_sensor_policy
                  add column if not exists rain_alert_enabled boolean not null default false;
                """
            )
            self._opening_schema_ready = True

    def ensure_notes_schema(self):
        if self._notes_schema_ready:
            return
        with self._notes_schema_lock:
            if self._notes_schema_ready:
                return
            self.execute_sql(
                """
                create table if not exists hc.notes (
                  id bigserial primary key,
                  type text not null check (type in ('issues', 'requests')),
                  text text not null check (length(trim(text)) > 0),
                  comment text not null default '',
                  done boolean not null default false,
                  created_at timestamptz not null default now(),
                  updated_at timestamptz not null default now()
                );

                alter table hc.notes
                  add column if not exists comment text not null default '';

                create index if not exists ix_notes_type_done_created_at
                  on hc.notes (type, done, created_at desc);

                create index if not exists ix_notes_created_at
                  on hc.notes (created_at desc);
                """
            )
            self._notes_schema_ready = True

    def fetch_notes(self):
        self.ensure_notes_schema()
        rows = self.fetch_all(
            """
            select id, type, text, comment, done, created_at, updated_at
            from hc.notes
            order by done asc, created_at desc, id desc
            """
        )
        result = {"issues": [], "requests": []}
        for row in rows:
            item = dict(row)
            note_type = item.get("type")
            if note_type in result:
                result[note_type].append(item)
        return self.json_ready(result)

    def note_payload(self, data: dict, require_text: bool = True):
        note_type = self.normalize_text(data.get("type"))
        if note_type not in {"issues", "requests"}:
            raise ValueError("type must be issues or requests")
        text = self.normalize_text(data.get("text"))
        if require_text and not text:
            raise ValueError("text is required")
        return {
            "type": note_type,
            "text": text,
            "comment": self.normalize_text(data.get("comment")),
            "done": bool(data.get("done", False)),
        }

    def create_note(self, data: dict):
        payload = self.note_payload(data)
        row = self.execute_one(
            """
            insert into hc.notes (type, text, comment, done)
            values (%s, %s, %s, %s)
            returning id, type, text, comment, done, created_at, updated_at
            """,
            (payload["type"], payload["text"], payload["comment"], payload["done"]),
        )
        self.invalidate_context("notes")
        return {"ok": True, "note": self.json_ready(row), "notes": self.fetch_notes(), "context": self.context_meta("notes")}

    def update_note(self, note_id: int, data: dict):
        values = []
        assignments = []
        if "text" in data:
            text = self.normalize_text(data.get("text"))
            if not text:
                raise ValueError("text is required")
            assignments.append("text = %s")
            values.append(text)
        if "done" in data:
            assignments.append("done = %s")
            values.append(bool(data.get("done")))
        if "comment" in data:
            assignments.append("comment = %s")
            values.append(self.normalize_text(data.get("comment")))
        if not assignments:
            raise ValueError("nothing to update")
        values.append(note_id)
        row = self.execute_one(
            f"""
            update hc.notes
            set {", ".join(assignments)},
                updated_at = now()
            where id = %s
            returning id, type, text, comment, done, created_at, updated_at
            """,
            tuple(values),
        )
        if not row:
            return None
        self.invalidate_context("notes")
        return {"ok": True, "note": self.json_ready(row), "notes": self.fetch_notes(), "context": self.context_meta("notes")}

    def delete_note(self, note_id: int):
        row = self.execute_one("delete from hc.notes where id = %s returning id", (note_id,))
        if not row:
            return None
        self.invalidate_context("notes")
        return {"ok": True, "deleted_id": note_id, "notes": self.fetch_notes(), "context": self.context_meta("notes")}

    def bootstrap_payload(self):
        self.ensure_opening_schema()
        return {
            "devices": self.fetch_all(
                """
                select d.*, count(e.id) as entity_count
                from hc.device d
                left join hc.entity e on e.device_id = d.id
                group by d.id
                order by d.platform, d.location nulls last, d.name
                """
            ),
            "entities": self.fetch_all(
                """
                select e.id, e.device_id, e.name, e.topic_base, e.is_active,
                       d.platform, d.name as device_name, d.location,
                       osp.opening_type, osp.room_position, osp.opening_label, osp.has_mosquito_net,
                       coalesce(osp.rain_alert_enabled, false) as rain_alert_enabled,
                       p.status, p.last_seen_ts
                from hc.entity e
                join hc.device d on d.id = e.device_id
                left join hc.opening_sensor_policy osp on osp.entity_id = e.id
                left join hc.entity_presence p on p.entity_id = e.id
                order by d.platform, d.location nulls last, d.name, e.name
                """
            ),
            "metrics": self.fetch_all("select * from hc.metric order by key"),
            "entity_metrics": self.fetch_all(
                """
                select em.*, e.name as entity_name
                from hc.entity_metric em
                join hc.entity e on e.id = em.entity_id
                order by e.name, em.metric_key
                """
            ),
            "irrigation": self.irrigation_context(),
            "scheduler": self.scheduler_state(),
        }

    def create_metric(self, data: dict):
        key = self.normalize_text(data.get("key"))
        value_type = self.normalize_text(data.get("value_type"), "num")
        if not key:
            raise ValueError("key is required")
        if value_type not in {"num", "bool", "text", "json"}:
            raise ValueError("invalid value_type")
        row = self.execute_one(
            """
            insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
            values (%s, %s, %s, %s, %s, %s, %s, true)
            on conflict (key) do update set
              value_type = excluded.value_type,
              unit = excluded.unit,
              min_num = excluded.min_num,
              max_num = excluded.max_num,
              description = excluded.description,
              enforce_validation = excluded.enforce_validation,
              is_active = true
            returning *
            """,
            (
                key,
                value_type,
                data.get("unit") or None,
                data.get("min_num"),
                data.get("max_num"),
                data.get("description") or None,
                bool(data.get("enforce_validation", True)),
            ),
        )
        self.invalidate_context(*self.CONTEXT_SECTIONS)
        return {"ok": True, "metric": row, "context": self.context_meta(*self.CONTEXT_SECTIONS)}

    def _device_payload(self, data: dict):
        platform = self.normalize_text(data.get("platform"), "zigbee")
        if platform not in {"zigbee", "tuya", "wifi", "system", "other"}:
            raise ValueError("invalid platform")
        name = self.normalize_text(data.get("name"))
        entity_name = self.normalize_text(data.get("entity_name"), name)
        topic_base = self.normalize_text(data.get("topic_base"))
        ext_id = self.normalize_text(data.get("ext_id"))
        if not name or not entity_name:
            raise ValueError("device and entity name are required")
        return platform, name, entity_name, topic_base, ext_id

    def _upsert_metric_rules(self, cur, entity_id: int, rules):
        for rule in rules or []:
            metric_key = self.normalize_text(rule.get("metric_key"))
            if not metric_key:
                continue
            cur.execute(
                """
                insert into hc.entity_metric
                  (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (entity_id, metric_key) do update set
                  store_mode = excluded.store_mode,
                  deadband_num = excluded.deadband_num,
                  min_interval_sec = excluded.min_interval_sec,
                  max_interval_sec = excluded.max_interval_sec,
                  is_enabled = excluded.is_enabled
                """,
                (
                    entity_id,
                    metric_key,
                    rule.get("store_mode") or "both",
                    rule.get("deadband_num"),
                    rule.get("min_interval_sec"),
                    rule.get("max_interval_sec"),
                    bool(rule.get("is_enabled", True)),
                ),
            )

    def _upsert_opening_policy(self, cur, entity_id: int, data: dict):
        opening_type = self.normalize_text(data.get("opening_type"), "window")
        if opening_type not in {"window", "door"}:
            opening_type = "window"
        room_position = data.get("room_position")
        if room_position in ("", None):
            room_position = None
        elif room_position is not None:
            room_position = int(room_position)
        opening_label = self.normalize_text(data.get("opening_label")) or None
        has_mosquito_net = bool(data.get("has_mosquito_net", False))
        rain_alert_enabled = bool(data.get("rain_alert_enabled", False))
        rules = data.get("metric_rules") or []
        has_contact_rule = any(self.normalize_text(rule.get("metric_key")) == "contact" for rule in rules)
        if not has_contact_rule and not any(key in data for key in ("opening_type", "room_position", "opening_label", "has_mosquito_net", "rain_alert_enabled")):
            return
        self.ensure_opening_schema()
        cur.execute(
            """
            insert into hc.opening_sensor_policy (
              entity_id, opening_type, room_position, opening_label, has_mosquito_net, rain_alert_enabled, updated_at
            )
            values (%s, %s, %s, %s, %s, %s, now())
            on conflict (entity_id) do update set
              opening_type = excluded.opening_type,
              room_position = excluded.room_position,
              opening_label = excluded.opening_label,
              has_mosquito_net = excluded.has_mosquito_net,
              rain_alert_enabled = excluded.rain_alert_enabled,
              updated_at = now()
            """,
            (entity_id, opening_type, room_position, opening_label, has_mosquito_net, rain_alert_enabled),
        )

    def create_device_with_entity(self, data: dict):
        platform, name, entity_name, topic_base, ext_id = self._device_payload(data)
        with self.db_conn(self.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
                    values (%s, %s, %s, %s, %s, %s, true)
                    on conflict (platform, ext_id) do update set
                      name = excluded.name,
                      location = excluded.location,
                      model = excluded.model,
                      manufacturer = excluded.manufacturer,
                      is_active = true,
                      updated_at = now()
                    returning *
                    """,
                    (
                        platform,
                        ext_id or None,
                        name,
                        data.get("location") or None,
                        data.get("model") or None,
                        data.get("manufacturer") or None,
                    ),
                )
                device = cur.fetchone()
                cur.execute(
                    """
                    insert into hc.entity (device_id, name, topic_base, is_active)
                    values (%s, %s, %s, true)
                    on conflict (device_id, name) do update set
                      topic_base = excluded.topic_base,
                      is_active = true
                    returning *
                    """,
                    (device["id"], entity_name, topic_base or None),
                )
                entity = cur.fetchone()
                self._upsert_metric_rules(cur, entity["id"], data.get("metric_rules", []))
                self._upsert_opening_policy(cur, entity["id"], data)
        self.invalidate_context(*self.CONTEXT_SECTIONS)
        return {"ok": True, "device": device, "entity": entity, "context": self.context_meta(*self.CONTEXT_SECTIONS)}

    def update_device_with_entity(self, device_id: int, data: dict):
        platform, name, entity_name, topic_base, ext_id = self._device_payload(data)
        if ext_id:
            conflict = self.fetch_one(
                """
                select id, name
                from hc.device
                where platform = %s
                  and ext_id = %s
                  and id <> %s
                """,
                (platform, ext_id, device_id),
            )
            if conflict:
                return {"ok": False, "error": f"address already belongs to {conflict['name']}"}, 409

        with self.db_conn(self.dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update hc.device
                    set platform = %s,
                        ext_id = %s,
                        name = %s,
                        location = %s,
                        model = %s,
                        manufacturer = %s,
                        is_active = true,
                        updated_at = now()
                    where id = %s
                    returning *
                    """,
                    (
                        platform,
                        ext_id or None,
                        name,
                        data.get("location") or None,
                        data.get("model") or None,
                        data.get("manufacturer") or None,
                        device_id,
                    ),
                )
                device = cur.fetchone()
                if not device:
                    return {"ok": False, "error": "device not found"}, 404

                cur.execute(
                    """
                    select *
                    from hc.entity
                    where device_id = %s
                    order by is_active desc, id
                    limit 1
                    """,
                    (device_id,),
                )
                entity = cur.fetchone()
                if entity:
                    cur.execute(
                        """
                        update hc.entity
                        set name = %s,
                            topic_base = %s,
                            is_active = true
                        where id = %s
                        returning *
                        """,
                        (entity_name, topic_base or None, entity["id"]),
                    )
                    entity = cur.fetchone()
                else:
                    cur.execute(
                        """
                        insert into hc.entity (device_id, name, topic_base, is_active)
                        values (%s, %s, %s, true)
                        returning *
                        """,
                        (device_id, entity_name, topic_base or None),
                    )
                    entity = cur.fetchone()
                self._upsert_metric_rules(cur, entity["id"], data.get("metric_rules", []))
                self._upsert_opening_policy(cur, entity["id"], data)

        self.api_cache_delete_prefix("power_wall_state")
        self.api_cache_delete_prefix("tuya_state")
        self.invalidate_context(*self.CONTEXT_SECTIONS)
        return {"ok": True, "device": device, "entity": entity, "context": self.context_meta(*self.CONTEXT_SECTIONS)}, 200

    def homecontrol_statistics_payload(self):
        self.ensure_opening_schema()
        cached = self.api_cache_get("homecontrol_statistics")
        if cached is not None:
            return cached
        rows = self.fetch_all(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              d.location,
              date_trunc('minute', m.ts) as ts,
              round(avg(m.v_num) filter (where m.key = 'temperature')::numeric, 2) as temperature,
              round(avg(m.v_num) filter (where m.key = 'humidity')::numeric, 2) as humidity
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            where m.key in ('temperature', 'humidity')
              and m.ts >= now() - interval '24 hours'
              and lower(e.name) not in ('moisture_01', 'moisture_02', 'moisture_03')
              and lower(d.name) not in ('moisture_01', 'moisture_02', 'moisture_03')
            group by e.id, e.name, d.name, d.location, date_trunc('minute', m.ts)
            order by e.name, date_trunc('minute', m.ts)
            """
        )
        sensors_by_id = {}
        for row in rows:
            sensor = sensors_by_id.setdefault(
                row["entity_id"],
                {
                    "entity_id": row["entity_id"],
                    "entity_name": row["entity_name"],
                    "device_name": row["device_name"],
                    "location": row["location"],
                    "samples": [],
                },
            )
            absolute_humidity = self.absolute_humidity_g_m3(row["temperature"], row["humidity"])
            sensor["samples"].append(
                {
                    "ts": row["ts"],
                    "temperature": row["temperature"],
                    "humidity": row["humidity"],
                    "absolute_humidity_g_m3": absolute_humidity,
                }
            )

        sensors = []
        for sensor in sensors_by_id.values():
            latest_temp = next((item["temperature"] for item in reversed(sensor["samples"]) if item["temperature"] is not None), None)
            latest_humidity = next((item["humidity"] for item in reversed(sensor["samples"]) if item["humidity"] is not None), None)
            latest_absolute_humidity = next((item["absolute_humidity_g_m3"] for item in reversed(sensor["samples"]) if item["absolute_humidity_g_m3"] is not None), None)
            latest_ts = sensor["samples"][-1]["ts"] if sensor["samples"] else None
            sensors.append(
                {
                    **sensor,
                    "latest_temperature": latest_temp,
                    "latest_humidity": latest_humidity,
                    "latest_absolute_humidity_g_m3": latest_absolute_humidity,
                    "latest_ts": latest_ts,
                    "sample_count": len(sensor["samples"]),
                }
            )

        sensors.sort(key=lambda item: item["entity_name"])
        opening_rows = self.fetch_all(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              d.location,
              coalesce(osp.opening_type, 'window') as opening_type,
              osp.room_position,
              osp.opening_label,
              coalesce(osp.has_mosquito_net, false) as has_mosquito_net,
              coalesce(osp.rain_alert_enabled, false) as rain_alert_enabled,
              contact.v_bool as contact,
              contact.ts as contact_ts,
              battery.v_num as battery,
              battery.ts as battery_ts,
              battery_low.v_bool as battery_low,
              linkquality.v_num as linkquality,
              greatest(
                coalesce(contact.ts, 'epoch'::timestamptz),
                coalesce(battery.ts, 'epoch'::timestamptz),
                coalesce(battery_low.ts, 'epoch'::timestamptz),
                coalesce(linkquality.ts, 'epoch'::timestamptz)
              ) as latest_ts
            from hc.entity e
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id and em.metric_key = 'contact' and em.is_enabled = true
            left join hc.opening_sensor_policy osp on osp.entity_id = e.id
            left join hc.entity_state contact on contact.entity_id = e.id and contact.key = 'contact'
            left join hc.entity_state battery on battery.entity_id = e.id and battery.key = 'battery'
            left join hc.entity_state battery_low on battery_low.entity_id = e.id and battery_low.key = 'battery_low'
            left join hc.entity_state linkquality on linkquality.entity_id = e.id and linkquality.key = 'linkquality'
            where e.is_active = true
              and d.is_active = true
            order by d.location nulls last, osp.room_position nulls last, e.name
            """
        )
        return self.api_cache_set(
            "homecontrol_statistics",
            {"temp_humidity_sensors": sensors, "opening_sensors": opening_rows},
            5,
        )
