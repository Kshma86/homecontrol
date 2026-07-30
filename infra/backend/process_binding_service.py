import threading
from typing import Any, Callable, Dict


PROCESS_BINDING_DEFINITIONS = {
    "irrigation_soil_moisture": {
        "process_key": "irrigation_soil_moisture",
        "label": "Irrigation soil moisture",
        "domain": "irrigation",
        "purpose": "Sensor used by the irrigation pilot soil moisture calculation.",
        "candidate_metric_keys": ("soil_moisture",),
        "fallback_topic_base": "zigbee/0xa4c13844a0908898",
        "context_sections": ("irrigation_pilot", "irrigation_statistics", "weather"),
    },
    "marten_power_socket": {
        "process_key": "marten_power_socket",
        "label": "Marten deterrent socket",
        "domain": "power_wall",
        "purpose": "Socket shown and scheduled by the marten deterrent controls.",
        "candidate_metric_keys": (
            "switch_state",
            "state",
            "power",
            "power_w",
            "current",
            "current_a",
            "mains_voltage_v",
            "voltage_v",
            "energy_kwh",
        ),
        "fallback_name_contains": "nyestriaszt",
        "context_sections": ("power_wall",),
    },
    "marten_motion_sensor": {
        "process_key": "marten_motion_sensor",
        "label": "Marten deterrent motion sensor",
        "domain": "power_wall",
        "purpose": "PIR sensor used to log movement near the marten deterrent.",
        "candidate_metric_keys": ("occupancy", "motion", "presence", "battery", "battery_low", "linkquality"),
        "fallback_topic_base": "zigbee/0xa4c1386aa4a76dd5",
        "context_sections": ("power_wall",),
    },
    "climate_extra_fan_socket": {
        "process_key": "climate_extra_fan_socket",
        "label": "Climate extra fan socket",
        "domain": "climate",
        "purpose": "Socket switched together with the climate unit.",
        "candidate_metric_keys": (
            "switch_state",
            "state",
            "power",
            "power_w",
            "current",
            "current_a",
            "mains_voltage_v",
            "voltage_v",
            "energy_kwh",
        ),
        "fallback_auto_climate": True,
        "context_sections": ("climate", "power_wall"),
    },
    "climate_power_meter": {
        "process_key": "climate_power_meter",
        "label": "Climate power meter",
        "domain": "climate",
        "purpose": "Meter used for climate power and energy statistics.",
        "candidate_metric_keys": ("power_w", "energy_kwh", "current_a", "voltage_v"),
        "fallback_ext_id_key": "climate_power_meter_ext_id",
        "context_sections": ("climate", "climate_power_history"),
    },
    "ai_node_power_plug": {
        "process_key": "ai_node_power_plug",
        "label": "AI node power plug",
        "domain": "ai",
        "purpose": "Plug used to power the remote AI machine.",
        "candidate_metric_keys": (
            "switch_state",
            "state",
            "power",
            "power_w",
            "current",
            "current_a",
            "energy_kwh",
        ),
        "fallback_entity_id_key": "ai_node_power_entity_id",
        "context_sections": ("power_wall",),
    },
    "hc_server_power_meter": {
        "process_key": "hc_server_power_meter",
        "label": "HC server power meter",
        "domain": "performance",
        "purpose": "Meter used for HomeControl server power statistics.",
        "candidate_metric_keys": ("power_w", "energy_kwh", "current_a", "voltage_v"),
        "fallback_name_contains": "hc szerver",
        "fallback_ext_id": "bf6ac883a687a6a2a2ci8l",
        "context_sections": ("performance", "server_power"),
    },
}


class ProcessBindingService:
    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        execute_one: Callable[..., Any],
        execute_sql: Callable[..., Any],
        normalize_text: Callable[..., str],
        api_cache_delete_prefix: Callable[[str], Any],
        invalidate_context: Callable[..., Any],
        invalidate_pilot: Callable[[], Any] = None,
        invalidate_weather_summary: Callable[[], Any] = None,
        legacy_fallbacks: Dict[str, Any] = None,
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.execute_one = execute_one
        self.execute_sql = execute_sql
        self.normalize_text = normalize_text
        self.api_cache_delete_prefix = api_cache_delete_prefix
        self.invalidate_context = invalidate_context
        self.invalidate_pilot = invalidate_pilot
        self.invalidate_weather_summary = invalidate_weather_summary
        self.legacy_fallbacks = legacy_fallbacks or {}
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def ensure_schema(self):
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            self.execute_sql(PROCESS_BINDING_SCHEMA_SQL)
            self._schema_ready = True

    def definition(self, process_key: str):
        key = self.normalize_text(process_key)
        if key not in PROCESS_BINDING_DEFINITIONS:
            raise ValueError("unknown process binding")
        return PROCESS_BINDING_DEFINITIONS[key]

    def candidate_entities(self, process_key: str):
        definition = self.definition(process_key)
        metrics = list(definition["candidate_metric_keys"])
        return self.fetch_all(
            """
            select
              e.id as entity_id,
              e.name as entity_name,
              coalesce(wp.display_name, e.name) as display_name,
              e.topic_base,
              d.id as device_id,
              d.platform,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              array_agg(distinct em.metric_key order by em.metric_key) as metrics
            from hc.entity e
            join hc.device d on d.id = e.device_id
            join hc.entity_metric em on em.entity_id = e.id
            left join hc.power_wall_policy wp on wp.entity_id = e.id
            where e.is_active = true
              and d.is_active = true
              and em.is_enabled = true
              and em.metric_key = any(%s)
            group by e.id, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
            order by d.platform, coalesce(d.location, ''), e.name
            """,
            (metrics,),
        )

    def fallback_entity(self, process_key: str):
        definition = self.definition(process_key)
        if definition.get("fallback_topic_base"):
            return self.fetch_one(
                """
                select
                  e.id as entity_id,
                  e.name as entity_name,
                  coalesce(wp.display_name, e.name) as display_name,
                  e.topic_base,
                  d.id as device_id,
                  d.platform,
                  d.name as device_name,
                  d.location,
                  d.model,
                  d.manufacturer,
                  array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
                from hc.entity e
                join hc.device d on d.id = e.device_id
                left join hc.power_wall_policy wp on wp.entity_id = e.id
                left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled = true
                where e.is_active = true
                  and d.is_active = true
                  and e.topic_base = %s
                group by e.id, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
                limit 1
                """,
                (definition["fallback_topic_base"],),
            )
        fallback_entity_id = self.legacy_fallbacks.get(definition.get("fallback_entity_id_key"))
        if fallback_entity_id:
            return self.fetch_one(
                """
                select
                  e.id as entity_id,
                  e.name as entity_name,
                  coalesce(wp.display_name, e.name) as display_name,
                  e.topic_base,
                  d.id as device_id,
                  d.platform,
                  d.name as device_name,
                  d.location,
                  d.model,
                  d.manufacturer,
                  array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
                from hc.entity e
                join hc.device d on d.id = e.device_id
                left join hc.power_wall_policy wp on wp.entity_id = e.id
                left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled = true
                where e.is_active = true
                  and d.is_active = true
                  and e.id = %s
                group by e.id, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
                limit 1
                """,
                (fallback_entity_id,),
            )
        fallback_ext_id = definition.get("fallback_ext_id") or self.legacy_fallbacks.get(definition.get("fallback_ext_id_key"))
        if fallback_ext_id:
            return self.fetch_one(
                """
                select
                  e.id as entity_id,
                  e.name as entity_name,
                  coalesce(wp.display_name, e.name) as display_name,
                  e.topic_base,
                  d.id as device_id,
                  d.platform,
                  d.name as device_name,
                  d.location,
                  d.model,
                  d.manufacturer,
                  array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
                from hc.entity e
                join hc.device d on d.id = e.device_id
                left join hc.power_wall_policy wp on wp.entity_id = e.id
                left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled = true
                where e.is_active = true
                  and d.is_active = true
                  and d.ext_id = %s
                group by e.id, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
                order by e.id
                limit 1
                """,
                (fallback_ext_id,),
            )
        if definition.get("fallback_auto_climate"):
            return self.fetch_one(
                """
                select
                  e.id as entity_id,
                  e.name as entity_name,
                  coalesce(wp.display_name, e.name) as display_name,
                  e.topic_base,
                  d.id as device_id,
                  d.platform,
                  d.name as device_name,
                  d.location,
                  d.model,
                  d.manufacturer,
                  array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
                from hc.power_wall_policy wp
                join hc.entity e on e.id = wp.entity_id
                join hc.device d on d.id = e.device_id
                left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled = true
                where wp.auto_climate = true
                  and e.is_active = true
                  and d.is_active = true
                group by e.id, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
                order by e.name
                limit 1
                """,
            )
        if definition.get("fallback_name_contains"):
            return self.fetch_one(
                """
                select
                  e.id as entity_id,
                  e.name as entity_name,
                  coalesce(wp.display_name, e.name) as display_name,
                  e.topic_base,
                  d.id as device_id,
                  d.platform,
                  d.name as device_name,
                  d.location,
                  d.model,
                  d.manufacturer,
                  array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
                from hc.entity e
                join hc.device d on d.id = e.device_id
                left join hc.power_wall_policy wp on wp.entity_id = e.id
                left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled = true
                where e.is_active = true
                  and d.is_active = true
                  and lower(e.name) like %s
                group by e.id, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
                order by e.name
                limit 1
                """,
                (f"%{definition['fallback_name_contains'].lower()}%",),
            )
        return None

    def stored_binding(self, process_key: str):
        self.ensure_schema()
        return self.fetch_one(
            """
            select
              pb.process_key,
              pb.entity_id,
              pb.updated_at,
              e.name as entity_name,
              coalesce(wp.display_name, e.name) as display_name,
              e.topic_base,
              d.id as device_id,
              d.platform,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
            from hc.process_sensor_binding pb
            left join hc.entity e on e.id = pb.entity_id and e.is_active = true
            left join hc.device d on d.id = e.device_id and d.is_active = true
            left join hc.power_wall_policy wp on wp.entity_id = e.id
            left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled = true
            where pb.process_key = %s
            group by pb.process_key, pb.entity_id, pb.updated_at, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
            """,
            (process_key,),
        )

    def binding(self, process_key: str, include_candidates: bool = False):
        definition = self.definition(process_key)
        stored = self.stored_binding(process_key)
        selected = stored if stored and stored.get("entity_id") and stored.get("entity_name") else self.fallback_entity(process_key)
        payload = {
            **definition,
            "candidate_metric_keys": list(definition["candidate_metric_keys"]),
            "context_sections": list(definition["context_sections"]),
            "selected_entity_id": selected.get("entity_id") if selected else None,
            "selected_entity": selected,
            "stored_entity_id": stored.get("entity_id") if stored else None,
            "uses_fallback": not bool(stored and stored.get("entity_id") and stored.get("entity_name")),
        }
        if include_candidates:
            payload["candidates"] = self.candidate_entities(process_key)
        return payload

    def payload(self):
        return {
            "ok": True,
            "bindings": {
                key: self.binding(key, include_candidates=True)
                for key in PROCESS_BINDING_DEFINITIONS
            },
        }

    def selected_topic_base(self, process_key: str):
        selected = self.binding(process_key).get("selected_entity") or {}
        return selected.get("topic_base")

    def selected_entity_id(self, process_key: str):
        selected = self.binding(process_key).get("selected_entity") or {}
        return selected.get("entity_id")

    def set_binding(self, process_key: str, entity_id: Any):
        definition = self.definition(process_key)
        try:
            selected_id = int(entity_id)
        except (TypeError, ValueError):
            raise ValueError("entity_id must be numeric")
        candidate_ids = {int(row["entity_id"]) for row in self.candidate_entities(process_key)}
        if selected_id not in candidate_ids:
            raise ValueError("entity is not a valid candidate for this process")
        row = self.execute_one(
            """
            insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
            values (%s, %s, now())
            on conflict (process_key) do update set
              entity_id = excluded.entity_id,
              updated_at = now()
            returning *
            """,
            (process_key, selected_id),
        )
        if process_key == "irrigation_soil_moisture":
            entity = self.fetch_one("select topic_base from hc.entity where id = %s", (selected_id,))
            self.execute_one(
                """
                update hc.irrigation_pilot_config
                set soil_sensor_topic_base = %s,
                    updated_at = now()
                where id = 1
                returning id
                """,
                ((entity or {}).get("topic_base") or definition["fallback_topic_base"],),
            )
            if self.invalidate_pilot:
                self.invalidate_pilot()
            if self.invalidate_weather_summary:
                self.invalidate_weather_summary()
        if process_key == "climate_extra_fan_socket":
            self.execute_one(
                """
                insert into hc.power_wall_policy (entity_id, auto_climate, updated_at)
                values (%s, true, now())
                on conflict (entity_id) do update set
                  auto_climate = true,
                  updated_at = now()
                returning entity_id
                """,
                (selected_id,),
            )
        for prefix in (
            "power_wall_state",
            "tuya_state",
            "process_bindings",
            "irrigation_pilot",
            "irrigation_weather_summary",
            "climate_power_history",
            "performance_server_power",
            "performance_snapshot",
        ):
            self.api_cache_delete_prefix(prefix)
        self.invalidate_context(*definition["context_sections"])
        return {"ok": True, "binding": self.binding(process_key, include_candidates=True), "stored": row}


PROCESS_BINDING_SCHEMA_SQL = """
create table if not exists hc.process_sensor_binding (
  process_key text primary key,
  entity_id bigint references hc.entity(id) on delete set null,
  updated_at timestamptz not null default now()
);

create index if not exists ix_process_sensor_binding_entity
  on hc.process_sensor_binding (entity_id);
"""
