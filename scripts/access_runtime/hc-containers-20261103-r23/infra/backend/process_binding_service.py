from runtime_schema_contract import check_runtime_schema
import threading
from typing import Any, Callable, Dict


PROCESS_BINDING_DEFINITIONS = {
    "combustion_extractor": {
        "process_key": "combustion_extractor", "label": "Combustion safety extractor",
        "domain": "combustion_safety", "purpose": "Power-meter socket used to detect and stop the kitchen extractor.",
        "candidate_metric_keys": ("power", "power_w", "switch_state"),
        "exclude_metric_keys": ("contact", "smoke", "carbon_monoxide"),
        "fallback_topic_base": "zigbee/0xa4c13812631a96d4", "context_sections": ("combustion_safety",),
    },
    "combustion_indicator": {
        "process_key": "combustion_indicator", "label": "Combustion safety indicator light",
        "domain": "combustion_safety", "purpose": "Colour light dedicated to local extractor safety signalling.",
        "candidate_metric_keys": ("switch_state", "brightness", "color", "color_temp"),
        "fallback_topic_base": "zigbee/0xe8ca50e272a90000", "context_sections": ("combustion_safety",),
    },
    "combustion_co_sensor": {
        "process_key": "combustion_co_sensor", "label": "Combustion safety CO sensor",
        "domain": "combustion_safety", "purpose": "CO alarm and concentration source for the supplementary guard.",
        "candidate_metric_keys": ("carbon_monoxide", "carbon_monoxide_value", "co", "co_ppm"),
        "fallback_topic_base": "zigbee/0xa4c1386ab8457e91", "context_sections": ("combustion_safety",),
    },
    "combustion_smoke_sensor": {
        "process_key": "combustion_smoke_sensor", "label": "Combustion safety smoke sensor",
        "domain": "combustion_safety", "purpose": "Smoke/fire alarm source for the supplementary guard.",
        "candidate_metric_keys": ("smoke", "smoke_alarm", "fire", "alarm"),
        "fallback_topic_base": "zigbee/0x403802fffeb11030",
        "context_sections": ("combustion_safety",),
    },
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
        "exclude_metric_keys": ("contact", "occupancy", "motion", "presence"),
        "fallback_name_contains": "nyestriaszt",
        "context_sections": ("power_wall",),
    },
    "marten_motion_sensor": {
        "process_key": "marten_motion_sensor",
        "label": "Marten deterrent motion sensor",
        "domain": "power_wall",
        "purpose": "PIR sensor used to log movement near the marten deterrent.",
        "candidate_metric_keys": ("occupancy", "motion", "presence"),
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
        "exclude_metric_keys": ("contact", "occupancy", "motion", "presence"),
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
        ai_power_coordinator=None,
        climate_fan_coordinator=None,
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
        self.ai_power_coordinator = ai_power_coordinator
        self.climate_fan_coordinator = climate_fan_coordinator
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def ensure_schema(self):
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            check_runtime_schema(self.execute_sql, "bindings")
            self._schema_ready = True

    def definition(self, process_key: str):
        key = self.normalize_text(process_key)
        if key not in PROCESS_BINDING_DEFINITIONS:
            raise ValueError("unknown process binding")
        return PROCESS_BINDING_DEFINITIONS[key]

    def candidate_entities(self, process_key: str, *, fetch_all=None):
        definition = self.definition(process_key)
        metrics = list(definition["candidate_metric_keys"])
        excluded_metrics = list(definition.get("exclude_metric_keys") or ())
        rows = (fetch_all or self.fetch_all)(
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
              and (
                cardinality(%s::text[]) = 0
                or not exists (
                  select 1
                  from hc.entity_metric em_excluded
                  where em_excluded.entity_id = e.id
                    and em_excluded.is_enabled = true
                    and em_excluded.metric_key = any(%s)
                )
              )
            group by e.id, e.name, wp.display_name, e.topic_base, d.id, d.platform, d.name, d.location, d.model, d.manufacturer
            order by d.platform, coalesce(d.location, ''), e.name
            """,
            (metrics, excluded_metrics, excluded_metrics),
        )

        return [row for row in rows if self.invalid_reason(process_key, row) is None]

    def fallback_entity(self, process_key: str, *, fetch_one=None):
        definition = self.definition(process_key)
        if definition.get("fallback_topic_base"):
            return (fetch_one or self.fetch_one)(
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
            return (fetch_one or self.fetch_one)(
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
            return (fetch_one or self.fetch_one)(
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
            return (fetch_one or self.fetch_one)(
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
            return (fetch_one or self.fetch_one)(
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

    def stored_binding(self, process_key: str, *, fetch_one=None):
        self.ensure_schema()
        return (fetch_one or self.fetch_one)(
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

    def invalid_reason(self, process_key, row):
        definition = self.definition(process_key)
        if not row or not row.get("entity_id") or not row.get("entity_name"):
            return "entity_missing_or_inactive"
        if not row.get("device_id"):
            return "device_missing_or_inactive"
        metrics = set(row.get("metrics") or ())
        if not metrics.intersection(definition["candidate_metric_keys"]):
            return "required_metric_unavailable"
        if metrics.intersection(definition.get("exclude_metric_keys") or ()):
            return "excluded_metric_present"
        switches = {"switch_state", "state"}
        if process_key in {"climate_extra_fan_socket", "marten_power_socket", "ai_node_power_plug", "combustion_extractor"}:
            if not metrics.intersection(switches):
                return "switch_capability_unavailable"
            if row.get("platform") not in {"zigbee", "tuya"}:
                return "unsupported_switch_platform"
        if process_key == "combustion_extractor" and not metrics.intersection({"power", "power_w"}):
            return "power_capability_unavailable"
        if process_key == "combustion_indicator":
            if not {"switch_state", "brightness", "color"}.issubset(metrics) or row.get("platform") != "zigbee":
                return "indicator_capability_unavailable"
        return None

    def binding(self, process_key: str, include_candidates: bool = False, *, fetch_one=None):
        definition = self.definition(process_key)
        key = definition["process_key"]
        stored = self.stored_binding(key, fetch_one=fetch_one)
        # A row remains explicit even after ON DELETE SET NULL. It must never
        # select a replacement through the initial-installation legacy fallback.
        candidate = stored if stored is not None else self.fallback_entity(key, fetch_one=fetch_one)
        reason = self.invalid_reason(key, candidate)
        selected = candidate if reason is None else None
        payload = {
            **definition,
            "candidate_metric_keys": list(definition["candidate_metric_keys"]),
            "context_sections": list(definition["context_sections"]),
            "configuration_state": ("valid" if selected else "invalid") if stored is not None else "not_configured",
            "invalid_reason": reason if selected is None else None,
            "selected_entity_id": selected.get("entity_id") if selected else None,
            "selected_entity": selected,
            "stored_entity_id": stored.get("entity_id") if stored else None,
            "uses_fallback": stored is None and selected is not None,
        }
        if include_candidates:
            payload["candidates"] = self.candidate_entities(key)
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
        # Keep the deployment guard before any schema/DB or service lookup.
        process_key = str(process_key or "").strip()
        from deployment_policy import ai_disabled, MESSAGE
        if process_key == 'ai_node_power_plug' and ai_disabled():
            raise ValueError(MESSAGE)
        if process_key == 'ai_node_power_plug' and self.ai_power_coordinator is not None:
            with self.ai_power_coordinator.locked() as state:
                self.ai_power_coordinator.invalidate(state, 'AI power binding update')
                return self._set_binding(process_key, entity_id)
        return self._set_binding(process_key, entity_id)

    def _set_binding(self, process_key: str, entity_id: Any):
        definition = self.definition(process_key)
        process_key = definition["process_key"]
        try:
            selected_id = int(entity_id)
        except (TypeError, ValueError):
            raise ValueError("entity_id must be numeric")
        candidate_ids = {int(row["entity_id"]) for row in self.candidate_entities(process_key)}
        if selected_id not in candidate_ids:
            raise ValueError("entity is not a valid candidate for this process")
        if process_key == "climate_extra_fan_socket":
            row = self._set_climate_binding(selected_id)
        else:
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

    def _set_climate_binding(self, selected_id):
        if self.climate_fan_coordinator is None:
            raise RuntimeError("climate fan coordination is required")
        self.ensure_schema()
        with self.climate_fan_coordinator.locked() as cur:
            def one(sql, params=()):
                cur.execute(sql, params)
                return cur.fetchone()
            def all_rows(sql, params=()):
                cur.execute(sql, params)
                return cur.fetchall()
            # Revalidate after waiting for another binding/policy/tick writer.
            if selected_id not in {int(r["entity_id"]) for r in self.candidate_entities("climate_extra_fan_socket", fetch_all=all_rows)}:
                raise ValueError("entity is not a valid candidate for this process")
            previous = self.binding("climate_extra_fan_socket", fetch_one=one)
            old_id = previous["selected_entity_id"] or previous["stored_entity_id"]
            if previous["selected_entity_id"] != selected_id:
                if old_id is not None:
                    one("""update hc.power_wall_policy set auto_climate = false,
                        auto_climate_on_at = null, updated_at = now()
                        where entity_id = %s returning entity_id""", (old_id,))
                # A->B->A cannot resurrect any old intent already on the new row.
                one("""update hc.power_wall_policy set auto_climate_on_at = null
                    where entity_id = %s returning entity_id""", (selected_id,))
            row = one("""insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
                values ('climate_extra_fan_socket', %s, now())
                on conflict (process_key) do update set entity_id = excluded.entity_id,
                updated_at = now() returning *""", (selected_id,))
            one("""insert into hc.power_wall_policy (entity_id, auto_climate, updated_at)
                values (%s, true, now()) on conflict (entity_id) do update set
                auto_climate = true, updated_at = now() returning entity_id""", (selected_id,))
        return row


PROCESS_BINDING_SCHEMA_SQL = """
create table if not exists hc.process_sensor_binding (
  process_key text primary key,
  entity_id bigint references hc.entity(id) on delete set null,
  updated_at timestamptz not null default now()
);

create index if not exists ix_process_sensor_binding_entity
  on hc.process_sensor_binding (entity_id);
"""
