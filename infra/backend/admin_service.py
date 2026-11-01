from runtime_schema_contract import check_runtime_schema
from startup_schema_contract import check_domain
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from settings import SETTINGS

RAIN_SENSOR_TOPIC_BASE = "zigbee/0xa4c138479ed598c1"
ZIGBEE2MQTT_DATABASE_PATH = os.getenv("ZIGBEE2MQTT_DATABASE_PATH", "")
ZIGBEE_RADIO_ONLINE_MAX_AGE_HOURS = 6


class AdminService:
    CONTEXT_SECTIONS = ("power_wall", "tuya", "irrigation", "climate", "home_statistics")

    PARAMETER_DESCRIPTIONS = {
        "mqtt_host": "Az MQTT broker hálózati neve vagy címe.",
        "mqtt_port": "Az MQTT broker portja.",
        "x10_base_topic": "A robotporszívó MQTT topic prefixe.",
        "climate_base_topic": "A klímavezérlés MQTT topic prefixe.",
        "gree_climate_ip": "A Gree klíma helyi IP-címe.",
        "gree_climate_port": "A Gree klíma helyi vezérlőportja.",
        "gree_climate_name": "A klíma megjelenített neve.",
        "ai_server_url": "A HomeControl AI átjáró belső címe.",
        "ai_server_timeout": "Az AI-kérések maximális várakozási ideje másodpercben.",
        "manual_max_minutes": "A kézi locsolás megengedett maximális hossza percben.",
        "scheduler_poll_seconds": "A locsolási scheduler ellenőrzési időköze másodpercben.",
        "weather_poll_seconds": "Az időjárási adatok lekérési időköze másodpercben.",
        "hc_context_realtime_ttl": "A valós idejű context gyorsítótár élettartama másodpercben.",
        "hc_context_statistics_ttl": "A statisztikai context gyorsítótár élettartama másodpercben.",
        "hc_context_refresh_seconds": "A háttér-context frissítési időköze másodpercben.",
        "hc_context_refresh_enabled": "Engedélyezi a context háttérben történő előmelegítését.",
        "power_wall_guard_seconds": "Kapcsolás utáni Power Wall védelmi idő másodpercben.",
        "power_wall_guard_repeat_seconds": "A Power Wall védelem ismétlési időköze másodpercben.",
    }

    FRONTEND_SYSTEM_PARAMETERS = (
        ("frontend.home.robot_refresh_ms", 5000, "A Home robotállapotának frissítési ideje."),
        ("frontend.home.climate_refresh_ms", 5000, "A Home klímaállapotának frissítési ideje."),
        ("frontend.home.power_wall_refresh_ms", 10000, "A Home Power Wall állapotának frissítési ideje."),
        ("frontend.home.scheduler_refresh_ms", 15000, "A Home scheduler-összefoglalójának frissítési ideje."),
        ("frontend.home.solar_refresh_ms", 30000, "A Home napelemes adatainak frissítési ideje."),
        ("frontend.solar.refresh_ms", 30000, "A Solar lap frissítési ideje."),
        ("frontend.robot.refresh_ms", 3000, "Az X10 lap robotállapotának frissítési ideje."),
        ("frontend.climate.state_refresh_ms", 10000, "A Climate lap klímaállapotának frissítési ideje."),
        ("frontend.climate.history_refresh_ms", 30000, "A Climate grafikonok frissítési ideje."),
        ("frontend.power_wall.refresh_ms", 10000, "A Power Wall lap frissítési ideje."),
        ("frontend.tuya.refresh_ms", 10000, "A Tuya lap frissítési ideje."),
        ("frontend.performance.refresh_ms", 60000, "A Performance lap automatikus frissítési ideje."),
        ("frontend.ai.status_refresh_ms", 30000, "A nyitott AI lap állapotellenőrzési ideje."),
        ("frontend.context.shared_max_age_ms", 2000, "Az azonos context-kérések kliensoldali összevonási időablaka."),
        ("frontend.bootstrap.retry_ms", 2000, "Sikertelen induló adatbetöltés utáni újrapróbálkozási idő."),
    )

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
        cached_api_payload: Callable[..., Any] = None,
    ):
        self.db_conn = db_conn
        self.dict_row = dict_row
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.execute_sql = execute_sql
        self.normalize_text = normalize_text
        self.json_ready = json_ready
        self.cached_api_payload = cached_api_payload or (lambda key, ttl, builder: builder())
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
        self._temperature_schema_ready = False
        self._temperature_schema_lock = threading.Lock()

    def ensure_temperature_schema(self):
        if self._temperature_schema_ready:
            return
        with self._temperature_schema_lock:
            if self._temperature_schema_ready:
                return
            check_runtime_schema(self.execute_sql, "temperature")
            self._temperature_schema_ready = True

    def ensure_opening_schema(self):
        if self._opening_schema_ready:
            return
        with self._opening_schema_lock:
            if self._opening_schema_ready:
                return
            check_runtime_schema(self.execute_sql, "opening")
            self._opening_schema_ready = True

    def ensure_notes_schema(self):
        if self._notes_schema_ready:
            return
        with self._notes_schema_lock:
            if self._notes_schema_ready:
                return
            check_domain(self.fetch_one, "notes")
            self._notes_schema_ready = True

    def latest_rain_sensor_snapshot(self):
        row = self.fetch_one(
            """
            select s.ts, s.v_bool
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            where e.topic_base = %s
              and s.key = 'water_leak'
            limit 1
            """,
            (RAIN_SENSOR_TOPIC_BASE,),
        )
        if not row:
            return {"is_wet": None, "ts": None}
        return {"is_wet": bool(row["v_bool"]) if row.get("v_bool") is not None else None, "ts": row.get("ts")}

    @staticmethod
    def zigbee_radio_status(ext_id: str):
        if not ZIGBEE2MQTT_DATABASE_PATH:
            return {"radio_online": None, "radio_last_seen_ts": None, "radio_age_hours": None}
        try:
            with open(ZIGBEE2MQTT_DATABASE_PATH, "r", encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    if row.get("ieeeAddr") != ext_id:
                        continue
                    last_seen_ms = row.get("lastSeen")
                    if not last_seen_ms:
                        break
                    last_seen = datetime.fromtimestamp(float(last_seen_ms) / 1000, tz=timezone.utc)
                    age_hours = max(0.0, (datetime.now(timezone.utc) - last_seen).total_seconds() / 3600)
                    return {
                        "radio_online": age_hours <= ZIGBEE_RADIO_ONLINE_MAX_AGE_HOURS,
                        "radio_last_seen_ts": last_seen,
                        "radio_age_hours": round(age_hours, 2),
                    }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return {"radio_online": None, "radio_last_seen_ts": None, "radio_age_hours": None}

    def fetch_notes(self, scope: str = "general"):
        self.ensure_notes_schema()
        note_scope = self.normalize_text(scope, "general")
        rows = self.fetch_all(
            """
            select id, scope, type, text, comment, done, coalesce(status, case when done then 'tested' else 'open' end) as status, created_at, updated_at
            from hc.notes
            where scope = %s
            order by
              case coalesce(status, case when done then 'tested' else 'open' end)
                when 'open' then 1
                when 'ready' then 2
                when 'testing' then 3
                when 'tested' then 4
                else 5
              end,
              created_at desc,
              id desc
            """,
            (note_scope,),
        )
        result = {"issues": [], "requests": []}
        for row in rows:
            item = dict(row)
            note_type = item.get("type")
            if note_type in result:
                result[note_type].append(item)
        return self.json_ready(result)

    def note_payload(self, data: dict, require_text: bool = True):
        scope = self.normalize_text(data.get("scope"), "general")
        if scope not in {"general", "mower"}:
            raise ValueError("invalid note scope")
        note_type = self.normalize_text(data.get("type"))
        if note_type not in {"issues", "requests"}:
            raise ValueError("type must be issues or requests")
        text = self.normalize_text(data.get("text"))
        if require_text and not text:
            raise ValueError("text is required")
        status = self.normalize_text(data.get("status"), "open")
        if status not in {"open", "ready", "testing", "tested"}:
            status = "open"
        return {
            "scope": scope,
            "type": note_type,
            "text": text,
            "comment": self.normalize_text(data.get("comment")),
            "done": bool(data.get("done", False)) or status == "tested",
            "status": status,
        }

    def create_note(self, data: dict):
        payload = self.note_payload(data)
        row = self.execute_one(
            """
            insert into hc.notes (scope, type, text, comment, done, status)
            values (%s, %s, %s, %s, %s, %s)
            returning id, scope, type, text, comment, done, status, created_at, updated_at
            """,
            (payload["scope"], payload["type"], payload["text"], payload["comment"], payload["done"], payload["status"]),
        )
        self.invalidate_context("notes")
        return {"ok": True, "note": self.json_ready(row), "notes": self.fetch_notes(payload["scope"]), "context": self.context_meta("notes")}

    def update_note(self, note_id: int, data: dict, scope: str = "general"):
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
            assignments.append("status = %s")
            values.append("tested" if data.get("done") else "open")
        if "status" in data:
            status = self.normalize_text(data.get("status"), "open")
            if status not in {"open", "ready", "testing", "tested"}:
                raise ValueError("invalid note status")
            assignments.append("status = %s")
            values.append(status)
            assignments.append("done = %s")
            values.append(status == "tested")
        if "comment" in data:
            assignments.append("comment = %s")
            values.append(self.normalize_text(data.get("comment")))
        if not assignments:
            raise ValueError("nothing to update")
        values.extend((note_id, self.normalize_text(scope, "general")))
        row = self.execute_one(
            f"""
            update hc.notes
            set {", ".join(assignments)},
                updated_at = now()
            where id = %s and scope = %s
            returning id, scope, type, text, comment, done, status, created_at, updated_at
            """,
            tuple(values),
        )
        if not row:
            return None
        self.invalidate_context("notes")
        return {"ok": True, "note": self.json_ready(row), "notes": self.fetch_notes(scope), "context": self.context_meta("notes")}

    def delete_note(self, note_id: int, scope: str = "general"):
        note_scope = self.normalize_text(scope, "general")
        row = self.execute_one("delete from hc.notes where id = %s and scope = %s returning id", (note_id, note_scope))
        if not row:
            return None
        self.invalidate_context("notes")
        return {"ok": True, "deleted_id": note_id, "notes": self.fetch_notes(note_scope), "context": self.context_meta("notes")}

    @staticmethod
    def _parameter_value_type(value):
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if value is None:
            return "null"
        return "text"

    def parameters_payload(self):
        """Return the read-only parameter inventory; never exposes credentials."""
        items = []
        hidden_runtime_fields = {"database_url", "openweather_api_key"}
        runtime_values = vars(SETTINGS)
        for key, raw_value in runtime_values.items():
            if key in hidden_runtime_fields:
                continue
            value = str(raw_value) if hasattr(raw_value, "__fspath__") else raw_value
            category = key.split("_", 1)[0]
            if key.startswith("hc_context") or key.startswith("api_perf"):
                category = "performance"
            elif key.startswith("irrigation") or key.startswith(("manual_", "scheduler_", "stop_", "open_")):
                category = "irrigation"
            elif key.startswith("gree_") or key.startswith("climate_"):
                category = "climate"
            elif key.startswith("ai_"):
                category = "ai"
            elif key.startswith("openweather_") or key == "weather_poll_seconds":
                category = "weather"
            items.append({
                "key": f"runtime.{key}",
                "name": key.replace("_", " ").capitalize(),
                "category": category,
                "source": "runtime configuration",
                "value": value,
                "value_type": self._parameter_value_type(value),
                "description": self.PARAMETER_DESCRIPTIONS.get(key, "A HomeControl futási konfigurációjának beállítása."),
                "read_only": True,
            })

        for key, value, description in self.FRONTEND_SYSTEM_PARAMETERS:
            items.append({
                "key": key,
                "name": key.removeprefix("frontend.").replace("_", " ").replace(".", " / ").capitalize(),
                "category": "frontend refresh",
                "source": "hard-coded frontend configuration",
                "value": value,
                "value_type": "integer",
                "description": description,
                "read_only": True,
            })

        items.sort(key=lambda item: (item["category"], item["source"], item["name"]))
        sources = sorted({item["source"] for item in items})
        categories = sorted({item["category"] for item in items})
        return {
            "ok": True,
            "read_only": True,
            "items": items,
            "summary": {"parameters": len(items), "sources": len(sources), "categories": len(categories)},
            "sources": sources,
            "categories": categories,
        }

    def bootstrap_payload(self):
        self.ensure_opening_schema()
        self.ensure_temperature_schema()
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
                       d.platform, d.ext_id, d.name as device_name, d.location, d.model, d.manufacturer,
                       osp.opening_type, osp.room_position, osp.opening_label, osp.has_mosquito_net,
                       coalesce(osp.rain_alert_enabled, false) as rain_alert_enabled,
                       coalesce(osp.climate_relevant, false) as climate_relevant,
                       coalesce(osp.extractor_air_role, 'none') as extractor_air_role,
                       coalesce(tsp.is_outdoor, false) as is_outdoor,
                       p.status, p.last_seen_ts
                from hc.entity e
                join hc.device d on d.id = e.device_id
                left join hc.opening_sensor_policy osp on osp.entity_id = e.id
                left join hc.temperature_sensor_policy tsp on tsp.entity_id = e.id
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
            "mqtt_flood_alerts": self.fetch_all(
                """
                select fs.topic_base, fs.active, fs.severity, fs.window_count,
                       fs.messages_per_minute, fs.first_exceeded_at, fs.detected_at,
                       fs.last_seen_at, fs.resolved_at, fs.updated_at,
                       e.name as entity_name, d.name as device_name, d.location
                from hc.mqtt_flood_state fs
                left join hc.entity e on e.id = fs.entity_id
                left join hc.device d on d.id = e.device_id
                where fs.active or fs.updated_at >= now() - interval '7 days'
                order by fs.active desc, fs.updated_at desc
                limit 50
                """
            ),
            "mqtt_flood_config": {
                "warning_per_minute": int(os.getenv("MQTT_FLOOD_WARNING_PER_MINUTE", "60")),
                "critical_per_minute": int(os.getenv("MQTT_FLOOD_CRITICAL_PER_MINUTE", "180")),
                "sustain_seconds": float(os.getenv("MQTT_FLOOD_SUSTAIN_SECONDS", "120")),
                "recovery_seconds": float(os.getenv("MQTT_FLOOD_RECOVERY_SECONDS", "120")),
            },
            "irrigation": self.irrigation_context(),
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
        climate_relevant = bool(data.get("climate_relevant", False))
        extractor_air_role = self.normalize_text(data.get("extractor_air_role"), "none")
        if extractor_air_role not in {"none", "secondary", "primary"}:
            raise ValueError("extractor_air_role must be none, secondary or primary")
        rules = data.get("metric_rules") or []
        has_contact_rule = any(self.normalize_text(rule.get("metric_key")) == "contact" for rule in rules)
        if not has_contact_rule:
            cur.execute("delete from hc.opening_sensor_policy where entity_id = %s", (entity_id,))
            return
        self.ensure_opening_schema()
        cur.execute(
            """
            insert into hc.opening_sensor_policy (
              entity_id, opening_type, room_position, opening_label, has_mosquito_net, rain_alert_enabled, climate_relevant, extractor_air_role, updated_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (entity_id) do update set
              opening_type = excluded.opening_type,
              room_position = excluded.room_position,
              opening_label = excluded.opening_label,
              has_mosquito_net = excluded.has_mosquito_net,
              rain_alert_enabled = excluded.rain_alert_enabled,
              climate_relevant = excluded.climate_relevant,
              extractor_air_role = excluded.extractor_air_role,
              updated_at = now()
            """,
            (entity_id, opening_type, room_position, opening_label, has_mosquito_net, rain_alert_enabled, climate_relevant, extractor_air_role),
        )

    def _upsert_temperature_policy(self, cur, entity_id: int, data: dict):
        rules = data.get("metric_rules") or []
        has_temperature_rule = any(self.normalize_text(rule.get("metric_key")) in {"temperature", "humidity"} for rule in rules)
        if not has_temperature_rule and "is_outdoor" not in data:
            return
        self.ensure_temperature_schema()
        cur.execute(
            """
            insert into hc.temperature_sensor_policy (entity_id, is_outdoor, updated_at)
            values (%s, %s, now())
            on conflict (entity_id) do update set
              is_outdoor = excluded.is_outdoor,
              updated_at = now()
            """,
            (entity_id, bool(data.get("is_outdoor", False))),
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
                self._upsert_temperature_policy(cur, entity["id"], data)
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
                self._upsert_temperature_policy(cur, entity["id"], data)

        self.api_cache_delete_prefix("power_wall_state")
        self.api_cache_delete_prefix("tuya_state")
        self.invalidate_context(*self.CONTEXT_SECTIONS)
        return {"ok": True, "device": device, "entity": entity, "context": self.context_meta(*self.CONTEXT_SECTIONS)}, 200

    def homecontrol_statistics_payload(self, range_key: str = "24h", hours: Any = None):
        self.ensure_opening_schema()
        self.ensure_temperature_schema()
        custom_hours = None
        try:
            custom_hours = int(hours) if hours not in (None, "") else None
        except (TypeError, ValueError):
            custom_hours = None
        if custom_hours is not None:
            custom_hours = max(1, min(custom_hours, 720))
            range_config = (f"{custom_hours} hours", "minute" if custom_hours <= 48 else "hour")
            range_label = f"{custom_hours}h"
        else:
            range_config = {
                "1h": ("1 hour", "minute"),
                "24h": ("24 hours", "minute"),
                "7d": ("7 days", "hour"),
            }.get(str(range_key or "24h").strip().lower(), ("24 hours", "minute"))
            range_label = "7d" if range_config[0] == "7 days" else "1h" if range_config[0] == "1 hour" else "24h"
        cache_key = f"homecontrol_statistics:{range_label}"
        return self.cached_api_payload(cache_key, 5, lambda: self._build_homecontrol_statistics_payload(range_label, range_config))

    def _build_homecontrol_statistics_payload(self, range_label, range_config):
        interval_text, bucket = range_config
        rows = self.fetch_all(
            f"""
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              d.location,
              coalesce(
                tsp.is_outdoor,
                lower(coalesce(e.name, '')) in ('udvar', 'yard', 'outside', 'outdoor')
                  or lower(coalesce(d.location, '')) in ('udvar', 'kert', 'kültér', 'kulter', 'outside', 'outdoor')
              ) as is_outdoor,
              date_trunc('{bucket}', m.ts) as ts,
              round(avg(m.v_num) filter (where m.key = 'temperature')::numeric, 2) as temperature,
              round(avg(m.v_num) filter (where m.key = 'humidity')::numeric, 2) as humidity,
              round(avg(m.v_num) filter (where m.key = 'pressure_hpa')::numeric, 1) as pressure_hpa
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            left join hc.temperature_sensor_policy tsp on tsp.entity_id = e.id
            where m.key in ('temperature', 'humidity', 'pressure_hpa')
              and m.ts >= now() - interval '{interval_text}'
              and lower(e.name) not in ('moisture_01', 'moisture_02', 'moisture_03')
              and lower(d.name) not in ('moisture_01', 'moisture_02', 'moisture_03')
            group by e.id, e.name, d.name, d.location, tsp.is_outdoor, date_trunc('{bucket}', m.ts)
            order by e.name, date_trunc('{bucket}', m.ts)
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
                    "is_outdoor": row["is_outdoor"],
                    "samples": [],
                },
            )
            absolute_humidity = self.absolute_humidity_g_m3(row["temperature"], row["humidity"])
            sensor["samples"].append(
                {
                    "ts": row["ts"],
                    "temperature": row["temperature"],
                    "humidity": row["humidity"],
                    "pressure_hpa": row["pressure_hpa"],
                    "absolute_humidity_g_m3": absolute_humidity,
                }
            )

        sensors = []
        for sensor in sensors_by_id.values():
            latest_temp = next((item["temperature"] for item in reversed(sensor["samples"]) if item["temperature"] is not None), None)
            latest_humidity = next((item["humidity"] for item in reversed(sensor["samples"]) if item["humidity"] is not None), None)
            latest_pressure = next((item["pressure_hpa"] for item in reversed(sensor["samples"]) if item["pressure_hpa"] is not None), None)
            latest_absolute_humidity = next((item["absolute_humidity_g_m3"] for item in reversed(sensor["samples"]) if item["absolute_humidity_g_m3"] is not None), None)
            latest_ts = sensor["samples"][-1]["ts"] if sensor["samples"] else None
            sensors.append(
                {
                    **sensor,
                    "latest_temperature": latest_temp,
                    "latest_humidity": latest_humidity,
                    "latest_pressure_hpa": latest_pressure,
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
              coalesce(osp.climate_relevant, false) as climate_relevant,
              coalesce(osp.extractor_air_role, 'none') as extractor_air_role,
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
        rain_sensor = self.latest_rain_sensor_snapshot()
        co_sensor = self.fetch_one(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              p.status,
              p.last_seen_ts,
              alarm.v_bool as carbon_monoxide,
              concentration.v_num as carbon_monoxide_value,
              fault.v_bool as fault,
              lifecycle.v_bool as lifecycle,
              battery_state.v_text as battery_state,
              nullif(greatest(
                coalesce(alarm.ts, 'epoch'::timestamptz),
                coalesce(concentration.ts, 'epoch'::timestamptz),
                coalesce(fault.ts, 'epoch'::timestamptz),
                coalesce(lifecycle.ts, 'epoch'::timestamptz),
                coalesce(battery_state.ts, 'epoch'::timestamptz)
              ), 'epoch'::timestamptz) as latest_ts
            from hc.device d
            join hc.entity e on e.device_id = d.id and e.is_active = true
            left join hc.entity_presence p on p.entity_id = e.id
            left join hc.entity_state alarm on alarm.entity_id = e.id and alarm.key = 'carbon_monoxide'
            left join hc.entity_state concentration on concentration.entity_id = e.id and concentration.key = 'carbon_monoxide_value'
            left join hc.entity_state fault on fault.entity_id = e.id and fault.key = 'fault'
            left join hc.entity_state lifecycle on lifecycle.entity_id = e.id and lifecycle.key = 'lifecycle'
            left join hc.entity_state battery_state on battery_state.entity_id = e.id and battery_state.key = 'battery_state'
            where d.platform = 'zigbee'
              and d.ext_id = '0xa4c1386ab8457e91'
              and d.is_active = true
            limit 1
            """
        )
        if co_sensor:
            co_sensor = {
                **co_sensor,
                **self.zigbee_radio_status("0xa4c1386ab8457e91"),
            }
        rain_sensor_wet = rain_sensor.get("is_wet") is True
        opening_rows = [
            {
                **row,
                "rain_alert_active": (
                    bool(row.get("rain_alert_enabled"))
                    and row.get("contact") is False
                    and rain_sensor_wet
                ),
                "rain_sensor_wet": rain_sensor.get("is_wet"),
                "rain_sensor_ts": rain_sensor.get("ts"),
            }
            for row in opening_rows
        ]
        opening_events = self.fetch_all(
            f"""
            with contact_rows as (
              select
                e.id as entity_id,
                e.name as entity_name,
                d.name as device_name,
                d.location,
                coalesce(osp.opening_type, 'window') as opening_type,
                osp.room_position,
                osp.opening_label,
                m.ts,
                m.v_bool as contact,
                lag(m.v_bool) over (partition by e.id order by m.ts) as previous_contact
              from hc.measurement m
              join hc.entity e on e.id = m.entity_id
              join hc.device d on d.id = e.device_id
              join hc.entity_metric em on em.entity_id = e.id and em.metric_key = 'contact' and em.is_enabled = true
              left join hc.opening_sensor_policy osp on osp.entity_id = e.id
              where m.key = 'contact'
                and m.v_bool is not null
                and e.is_active = true
                and d.is_active = true
                and m.ts >= now() - interval '{interval_text}' - interval '2 days'
            )
            select
              entity_id,
              entity_name,
              device_name,
              location,
              opening_type,
              room_position,
              opening_label,
              ts,
              contact
            from contact_rows
            where ts >= now() - interval '{interval_text}'
              and (previous_contact is null or previous_contact is distinct from contact)
            order by ts desc
            limit 200
            """
        )
        return {
                "temp_humidity_sensors": sensors,
                "opening_sensors": opening_rows,
                "opening_events": opening_events,
                "rain_sensor": rain_sensor,
                "co_sensor": co_sensor,
                "range": range_label,
                "bucket": bucket,
            }

