from typing import Any, Callable, Dict


class EnergyDeviceService:
    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        api_cache_get: Callable[[str], Any],
        api_cache_set: Callable[[str, Any, float], Any],
        json_ready: Callable[[Any], Any],
        solar_topic_base: str = "homecontrol/tele/growatt/cloud",
        process_binding_payload: Callable[[str], Any] = None,
        process_binding_entity_id: Callable[[str], Any] = None,
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.api_cache_get = api_cache_get
        self.api_cache_set = api_cache_set
        self.json_ready = json_ready
        self.solar_topic_base = solar_topic_base
        self.process_binding_payload = process_binding_payload
        self.process_binding_entity_id = process_binding_entity_id

    @staticmethod
    def state_value(row: Dict[str, Any]):
        value = row.get("v_num")
        if value is None:
            value = row.get("v_bool")
        if value is None:
            value = row.get("v_text")
        if value is None:
            value = row.get("v_json")
        return value

    def tuya_state_payload(self):
        cached = self.api_cache_get("tuya_state")
        if cached is not None:
            return cached
        devices = self.fetch_all(
            """
            select
              d.id as device_id,
              d.ext_id,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              p.status,
              p.last_seen_ts,
              p.updated_at as presence_updated_at
            from hc.device d
            join hc.entity e on e.device_id = d.id
            left join hc.entity_presence p on p.entity_id = e.id
            where d.platform = 'tuya'
              and d.is_active = true
              and e.is_active = true
            order by e.name
            """
        )
        entity_ids = [row["entity_id"] for row in devices]
        if not entity_ids:
            return self.api_cache_set(
                "tuya_state",
                {"devices": [], "state_rows": [], "recent_measurements": [], "summary": {"total": 0, "online": 0, "degraded": 0, "offline": 0}},
                8,
            )

        state_rows = self.fetch_all(
            """
            select
              s.entity_id,
              e.name as entity_name,
              s.key,
              s.ts,
              s.v_num,
              s.v_bool,
              s.v_text,
              s.v_json,
              s.meta
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            where s.entity_id = any(%s)
            order by e.name, s.key
            """,
            (entity_ids,),
        )
        recent_measurements = self.fetch_all(
            """
            select
              m.entity_id,
              e.name as entity_name,
              m.key,
              count(*) as sample_count,
              max(m.ts) as last_ts,
              avg(m.v_num) filter (where m.v_num is not null) as avg_num,
              max(m.v_num) filter (where m.v_num is not null) as max_num,
              min(m.v_num) filter (where m.v_num is not null) as min_num
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            where m.entity_id = any(%s)
              and m.ts > now() - interval '6 hours'
            group by m.entity_id, e.name, m.key
            order by e.name, m.key
            """,
            (entity_ids,),
        )

        state_by_entity: Dict[int, Dict[str, Any]] = {}
        for row in state_rows:
            state_by_entity.setdefault(row["entity_id"], {})[row["key"]] = {
                "value": self.state_value(row),
                "ts": row["ts"],
                "meta": row.get("meta"),
            }

        for row in devices:
            row["state"] = state_by_entity.get(row["entity_id"], {})
        statuses = [(row.get("status") or "unknown") for row in devices]
        summary = {
            "total": len(devices),
            "online": sum(1 for status in statuses if status == "online"),
            "degraded": sum(1 for status in statuses if status == "degraded"),
            "offline": sum(1 for status in statuses if status == "offline"),
            "unknown": sum(1 for status in statuses if status not in {"online", "degraded", "offline"}),
        }
        return self.api_cache_set("tuya_state", {"devices": devices, "state_rows": state_rows, "recent_measurements": recent_measurements, "summary": summary}, 8)

    def solar_state_payload(self):
        entity = self.fetch_one(
            """
            select
              d.id as device_id,
              d.ext_id,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              p.status,
              p.last_seen_ts,
              p.updated_at as presence_updated_at
            from hc.entity e
            join hc.device d on d.id = e.device_id
            left join hc.entity_presence p on p.entity_id = e.id
            where e.topic_base = %s
              and e.is_active = true
            limit 1
            """,
            (self.solar_topic_base,),
        )
        if not entity:
            return {"ok": False, "error": "Growatt cloud entity not found", "topic_base": self.solar_topic_base}

        state_rows = self.fetch_all(
            """
            select
              s.entity_id,
              e.name as entity_name,
              e.topic_base,
              s.key,
              s.ts,
              s.v_num,
              s.v_bool,
              s.v_text,
              s.v_json,
              s.meta
            from hc.entity_state s
            join hc.entity e on e.id = s.entity_id
            join hc.device d on d.id = e.device_id
            where d.platform = 'growatt'
              and e.is_active = true
            order by e.topic_base, s.key
            """
        )

        state: Dict[str, Any] = {}
        state_updated_at = None
        for row in state_rows:
            state[row["key"]] = {"value": self.state_value(row), "ts": row["ts"], "meta": row.get("meta")}
            if not state_updated_at or (row.get("ts") and row["ts"] > state_updated_at):
                state_updated_at = row["ts"]

        recent_measurements = self.fetch_all(
            """
            select
              m.key,
              count(*) as sample_count,
              max(m.ts) as last_ts,
              avg(m.v_num) filter (where m.v_num is not null) as avg_num,
              max(m.v_num) filter (where m.v_num is not null) as max_num,
              min(m.v_num) filter (where m.v_num is not null) as min_num
            from hc.measurement m
            join hc.entity e on e.id = m.entity_id
            join hc.device d on d.id = e.device_id
            where d.platform = 'growatt'
              and m.ts > now() - interval '24 hours'
            group by m.key
            order by m.key
            """
        )

        load_power_24h = self.fetch_all(
            """
            with hours as (
              select generate_series(
                date_trunc('hour', now()) - interval '23 hours',
                date_trunc('hour', now()),
                interval '1 hour'
              ) as ts
            ),
            load_samples as (
              select
                date_trunc('hour', m.ts) as ts,
                avg(m.v_num) as avg_load_power_w,
                max(m.v_num) as max_load_power_w,
                count(*) as sample_count
              from hc.measurement m
              join hc.entity e on e.id = m.entity_id
              join hc.device d on d.id = e.device_id
              where d.platform = 'growatt'
                and m.key = 'local_load_power_w'
                and m.ts >= date_trunc('hour', now()) - interval '23 hours'
                and m.v_num is not null
              group by date_trunc('hour', m.ts)
            )
            select
              h.ts,
              l.avg_load_power_w,
              l.max_load_power_w,
              coalesce(l.sample_count, 0) as sample_count
            from hours h
            left join load_samples l on l.ts = h.ts
            order by h.ts
            """
        )

        production_power_24h = self.fetch_all(
            """
            with hours as (
              select generate_series(
                date_trunc('hour', now()) - interval '23 hours',
                date_trunc('hour', now()),
                interval '1 hour'
              ) as ts
            ),
            production_samples as (
              select
                date_trunc('hour', m.ts) as ts,
                avg(m.v_num) as avg_production_power_w,
                max(m.v_num) as max_production_power_w,
                count(*) as sample_count
              from hc.measurement m
              join hc.entity e on e.id = m.entity_id
              join hc.device d on d.id = e.device_id
              where d.platform = 'growatt'
                and m.key in ('system_power_w', 'output_power_w', 'plant_output_power_w')
                and m.ts >= date_trunc('hour', now()) - interval '23 hours'
                and m.v_num is not null
              group by date_trunc('hour', m.ts)
            )
            select
              h.ts,
              p.avg_production_power_w,
              p.max_production_power_w,
              coalesce(p.sample_count, 0) as sample_count
            from hours h
            left join production_samples p on p.ts = h.ts
            order by h.ts
            """
        )

        production_daily_30d = self.fetch_all(
            """
            with days as (
              select generate_series(
                date_trunc('day', now()) - interval '29 days',
                date_trunc('day', now()),
                interval '1 day'
              )::date as day
            ),
            production as (
              select
                date_trunc('day', m.ts)::date as day,
                max(m.v_num) filter (where m.key = 'energy_today_kwh') as energy_today_kwh,
                max(m.v_num) filter (where m.key = 'plant_energy_today_kwh') as plant_energy_today_kwh,
                max(m.v_num) filter (where m.key = 'solar_energy_today_kwh') as solar_energy_today_kwh,
                count(*) as sample_count
              from hc.measurement m
              join hc.entity e on e.id = m.entity_id
              join hc.device d on d.id = e.device_id
              where d.platform = 'growatt'
                and m.key in ('energy_today_kwh', 'plant_energy_today_kwh', 'solar_energy_today_kwh')
                and m.ts >= date_trunc('day', now()) - interval '29 days'
                and m.v_num is not null
              group by date_trunc('day', m.ts)::date
            )
            select
              d.day,
              coalesce(p.energy_today_kwh, p.plant_energy_today_kwh, p.solar_energy_today_kwh, 0) as production_kwh,
              p.energy_today_kwh,
              p.plant_energy_today_kwh,
              p.solar_energy_today_kwh,
              coalesce(p.sample_count, 0) as sample_count
            from days d
            left join production p on p.day = d.day
            order by d.day
            """
        )

        production_month = self.fetch_one(
            """
            with daily as (
              select
                date_trunc('day', m.ts)::date as day,
                coalesce(
                  max(m.v_num) filter (where m.key = 'energy_today_kwh'),
                  max(m.v_num) filter (where m.key = 'plant_energy_today_kwh'),
                  max(m.v_num) filter (where m.key = 'solar_energy_today_kwh'),
                  0
                ) as production_kwh
              from hc.measurement m
              join hc.entity e on e.id = m.entity_id
              join hc.device d on d.id = e.device_id
              where d.platform = 'growatt'
                and m.key in ('energy_today_kwh', 'plant_energy_today_kwh', 'solar_energy_today_kwh')
                and m.ts >= date_trunc('month', now())
                and m.v_num is not null
              group by date_trunc('day', m.ts)::date
            )
            select
              coalesce(round(sum(production_kwh)::numeric, 1), 0) as production_month_kwh,
              count(*) as production_month_days
            from daily
            """
        ) or {}

        priority = [
            "system_power_w", "output_power_w", "plant_output_power_w", "energy_today_kwh",
            "plant_energy_today_kwh", "lifetime_energy_kwh", "plant_lifetime_energy_kwh",
            "battery_soc_percent", "local_load_power_w", "import_power_w", "export_power_w",
            "load_consumption_today_kwh", "export_to_grid_today_kwh", "input_1_wattage_w",
            "input_2_wattage_w", "growatt_grid_voltage_l1_v", "growatt_grid_voltage_l2_v",
            "growatt_grid_voltage_l3_v",
        ]
        current = {key: state.get(key, {}).get("value") for key in priority if key in state}
        summary = {
            "entity_count": state.get("entity_count", {}).get("value"),
            "state_count": len(state_rows),
            "measurement_count_24h": sum(int(row.get("sample_count") or 0) for row in recent_measurements),
            "updated_at": state_updated_at,
            "status": entity.get("status") or "unknown",
            "production_month_kwh": production_month.get("production_month_kwh"),
            "production_month_days": production_month.get("production_month_days") or 0,
        }

        return self.json_ready(
            {
                "ok": True,
                "entity": entity,
                "state": state,
                "current": current,
                "state_rows": state_rows,
                "recent_measurements": recent_measurements,
                "charts": {
                    "load_power_24h": load_power_24h,
                    "production_power_24h": production_power_24h,
                    "production_daily_30d": production_daily_30d,
                },
                "summary": summary,
            }
        )

    def server_power_history_payload(self):
        binding_entity_id = self.process_binding_entity_id("hc_server_power_meter") if self.process_binding_entity_id else None
        row = self.fetch_one(
            """
            select
              d.id as device_id,
              d.ext_id,
              d.name as device_name,
              d.location,
              d.model,
              d.manufacturer,
              e.id as entity_id,
              e.name as entity_name,
              e.topic_base,
              coalesce(wp.display_name, e.name) as display_name,
              p.status,
              p.last_seen_ts,
              p.updated_at as presence_updated_at
            from hc.device d
            join hc.entity e on e.device_id = d.id
            left join hc.power_wall_policy wp on wp.entity_id = e.id
            left join hc.entity_presence p on p.entity_id = e.id
            where d.is_active = true
              and e.is_active = true
              and (
                (%s::bigint is not null and e.id = %s::bigint)
                or (
                  %s::bigint is null
                  and d.platform = 'tuya'
                  and (
                    wp.display_name = 'HC szerver'
                    or d.ext_id = 'bf6ac883a687a6a2a2ci8l'
                    or lower(e.name) = 'hc szerver'
                  )
                )
              )
            order by
              case when %s::bigint is not null and e.id = %s::bigint then 0 else 1 end,
              case
                when wp.display_name = 'HC szerver' then 0
                when d.ext_id = 'bf6ac883a687a6a2a2ci8l' then 1
                else 2
              end,
              e.id
            limit 1
            """
            ,
            (binding_entity_id, binding_entity_id, binding_entity_id, binding_entity_id, binding_entity_id),
        )
        if not row:
            return {"ok": False, "error": "HC szerver plug entity not found", "power_24h": [], "daily_30d": []}

        state_rows = self.fetch_all(
            """
            select key, ts, v_num, v_bool, v_text, v_json
            from hc.entity_state
            where entity_id = %s
              and key in ('switch_state', 'power_w', 'current_a', 'voltage_v', 'energy_kwh', 'energy_calc_kwh', 'lag_sec')
            order by key
            """,
            (row["entity_id"],),
        )
        state: Dict[str, Any] = {}
        state_ts: Dict[str, Any] = {}
        for item in state_rows:
            state[item["key"]] = self.state_value(item)
            state_ts[item["key"]] = item.get("ts")

        power_rows = self.fetch_all(
            """
            select ts, v_num as power_w
            from hc.measurement
            where entity_id = %s
              and key = 'power_w'
              and ts >= now() - interval '24 hours'
              and v_num is not null
            order by ts
            """,
            (row["entity_id"],),
        )
        daily_rows = self.fetch_all(
            """
            with days as (
              select generate_series(
                date_trunc('day', now()) - interval '29 days',
                date_trunc('day', now()),
                interval '1 day'
              )::date as day
            ),
            energy as (
              select
                date_trunc('day', ts)::date as day,
                min(v_num) as first_energy_kwh,
                max(v_num) as last_energy_kwh,
                greatest(coalesce(max(v_num) - min(v_num), 0), 0) as energy_kwh,
                count(*) as sample_count
              from hc.measurement
              where entity_id = %s
                and key = 'energy_kwh'
                and ts >= date_trunc('day', now()) - interval '29 days'
                and v_num is not null
              group by 1
            )
            select
              d.day,
              coalesce(e.energy_kwh, 0) as energy_kwh,
              e.first_energy_kwh,
              e.last_energy_kwh,
              coalesce(e.sample_count, 0) as sample_count
            from days d
            left join energy e on e.day = d.day
            order by d.day
            """,
            (row["entity_id"],),
        )

        today = daily_rows[-1] if daily_rows else {}
        power_values = [item.get("power_w") for item in power_rows if item.get("power_w") is not None]
        return {
            "ok": True,
            "device": row,
            "process_bindings": {
                "hc_server_power_meter": self.process_binding_payload("hc_server_power_meter") if self.process_binding_payload else None,
            },
            "state": state,
            "state_ts": state_ts,
            "power_24h": power_rows,
            "daily_30d": daily_rows,
            "summary": {
                "power_samples": len(power_rows),
                "daily_days": len(daily_rows),
                "today_energy_kwh": today.get("energy_kwh"),
                "max_power_w": max((item.get("power_w") or 0 for item in power_rows), default=0),
                "avg_power_w_24h": round(sum(power_values) / len(power_values), 2) if power_values else None,
                "current_power_w": state.get("power_w"),
                "total_energy_kwh": state.get("energy_kwh"),
                "status": row.get("status") or "unknown",
                "updated_at": max((ts for ts in state_ts.values() if ts), default=row.get("last_seen_ts")),
            },
        }
