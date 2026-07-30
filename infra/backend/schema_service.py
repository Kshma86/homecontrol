from threading import Lock
from typing import Callable


class HcSchemaService:
    def __init__(self, execute_sql: Callable[[str], None]):
        self.execute_sql = execute_sql
        self._pilot_ready = False
        self._pilot_lock = Lock()
        self._power_wall_ready = False
        self._power_wall_lock = Lock()

    def ensure_pilot_schema(self) -> None:
        if self._pilot_ready:
            return
        with self._pilot_lock:
            if self._pilot_ready:
                return
            self.execute_sql(PILOT_SCHEMA_SQL)
            self._pilot_ready = True

    def ensure_power_wall_schema(self) -> None:
        if self._power_wall_ready:
            return
        with self._power_wall_lock:
            if self._power_wall_ready:
                return
            self.execute_sql(POWER_WALL_SCHEMA_SQL)
            self._power_wall_ready = True


PILOT_SCHEMA_SQL = """
insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('water_leak', 'bool', null, null, null, 'Rain sensor wet/dry state', false, true),
  ('battery_low', 'bool', null, null, null, 'Battery low flag', false, true),
  ('battery', 'num', '%', 0, 100, 'Battery percent', true, true),
  ('linkquality', 'num', null, 0, 255, 'Zigbee link quality', true, true)
on conflict (key) do update set
  value_type = excluded.value_type,
  unit = excluded.unit,
  min_num = excluded.min_num,
  max_num = excluded.max_num,
  description = excluded.description,
  enforce_validation = excluded.enforce_validation,
  is_active = true;

with device_upsert as (
  insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
  values ('zigbee', '0xa4c138479ed598c1', 'Rain sensor', 'Udvar', 'TS0207', 'Tuya', true)
  on conflict (platform, ext_id) do update set
    name = excluded.name,
    location = excluded.location,
    model = excluded.model,
    manufacturer = excluded.manufacturer,
    is_active = true,
    updated_at = now()
  returning id
)
insert into hc.entity (device_id, name, topic_base, is_active)
select id, 'Rain sensor', 'zigbee/0xa4c138479ed598c1', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('water_leak', 'both', null::double precision, 1, 86400),
  ('battery_low', 'both', null::double precision, 1, 86400),
  ('battery', 'both', 1::double precision, 3600, 86400),
  ('linkquality', 'both', null::double precision, 3600, 86400)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'zigbee' and d.ext_id = '0xa4c138479ed598c1'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

create table if not exists hc.irrigation_pilot_config (
  id smallint primary key default 1 check (id = 1),
  mode text not null default 'navigator' check (mode in ('navigator', 'pilot')),
  base_duration_minutes integer not null default 90 check (base_duration_minutes between 1 and 720),
  rain_24h_threshold_mm numeric not null default 5,
  forecast_rain_threshold_mm numeric not null default 5,
  pop_threshold_percent integer not null default 70 check (pop_threshold_percent between 0 and 100),
  heat_threshold_c numeric not null default 32,
  heat_correction_percent integer not null default 20,
  cold_threshold_c numeric not null default 22,
  cold_correction_percent integer not null default -20,
  soil_moisture_enabled boolean not null default true,
  soil_sensor_topic_base text not null default 'zigbee/0xa4c13844a0908898',
  soil_wet_skip_threshold_percent numeric not null default 85,
  soil_dry_threshold_percent numeric not null default 45,
  soil_dry_correction_percent integer not null default 15,
  soil_sample_max_age_hours integer not null default 12,
  updated_at timestamptz not null default now()
);

alter table hc.irrigation_pilot_config
  add column if not exists soil_moisture_enabled boolean not null default true,
  add column if not exists soil_sensor_topic_base text not null default 'zigbee/0xa4c13844a0908898',
  add column if not exists soil_wet_skip_threshold_percent numeric not null default 85,
  add column if not exists soil_dry_threshold_percent numeric not null default 45,
  add column if not exists soil_dry_correction_percent integer not null default 15,
  add column if not exists soil_sample_max_age_hours integer not null default 12;

insert into hc.irrigation_pilot_config (id)
values (1)
on conflict (id) do nothing;

create table if not exists hc.weather_observation (
  id bigserial primary key,
  ts timestamptz not null default now(),
  source text not null default 'openweathermap',
  temperature_c numeric,
  humidity_percent numeric,
  wind_speed_mps numeric,
  wind_deg numeric,
  rain_mm numeric,
  pop_percent numeric,
  uv_index numeric,
  cloudiness_percent numeric,
  pressure_hpa numeric,
  sunrise timestamptz,
  sunset timestamptz,
  forecast_rain_24h_mm numeric,
  forecast_pop_max_percent numeric,
  forecast_temp_max_c numeric,
  raw jsonb not null default '{}'::jsonb
);

create index if not exists ix_weather_observation_ts
  on hc.weather_observation (ts desc);

alter table hc.weather_observation
  add column if not exists wind_deg numeric;

create table if not exists hc.irrigation_pilot_decision (
  id bigserial primary key,
  timestamp timestamptz not null default now(),
  mode text not null check (mode in ('navigator', 'pilot')),
  base_duration integer not null,
  final_duration integer not null,
  executed boolean not null default false,
  reason text not null,
  triggered_rules jsonb not null default '[]'::jsonb,
  weather_snapshot jsonb not null default '{}'::jsonb,
  details jsonb not null default '{}'::jsonb,
  schedule_id bigint,
  execution_status text not null default 'not_executed'
);

create index if not exists ix_irrigation_pilot_decision_timestamp
  on hc.irrigation_pilot_decision (timestamp desc);
"""


POWER_WALL_SCHEMA_SQL = """
create table if not exists hc.power_wall_policy (
  entity_id bigint primary key references hc.entity(id) on delete cascade,
  display_name text,
  always_on boolean not null default false,
  auto_climate boolean not null default false,
  last_action_at timestamptz,
  last_action text,
  last_error text,
  updated_at timestamptz not null default now()
);

alter table hc.power_wall_policy
  add column if not exists display_name text;
alter table hc.power_wall_policy
  add column if not exists auto_climate boolean not null default false;
alter table hc.power_wall_policy
  add column if not exists scheduler_enabled boolean not null default false;
alter table hc.power_wall_policy
  add column if not exists scheduler_window_start time not null default '20:00';
alter table hc.power_wall_policy
  add column if not exists scheduler_window_end time not null default '06:00';
alter table hc.power_wall_policy
  add column if not exists scheduler_min_on_minutes integer not null default 12;
alter table hc.power_wall_policy
  add column if not exists scheduler_max_on_minutes integer not null default 35;
alter table hc.power_wall_policy
  add column if not exists scheduler_min_off_minutes integer not null default 20;
alter table hc.power_wall_policy
  add column if not exists scheduler_max_off_minutes integer not null default 90;
alter table hc.power_wall_policy
  add column if not exists scheduler_jitter_minutes integer not null default 5;

create table if not exists hc.power_wall_schedule_session (
  id bigserial primary key,
  entity_id bigint not null references hc.entity(id) on delete cascade,
  planned_start_at timestamptz not null,
  planned_end_at timestamptz,
  actual_start_at timestamptz,
  actual_end_at timestamptz,
  duration_minutes integer,
  status text not null default 'planned' check (status in ('planned', 'running', 'completed', 'cancelled', 'failed')),
  start_action jsonb,
  stop_action jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_power_wall_policy_always_on
  on hc.power_wall_policy (always_on, last_action_at);

create index if not exists ix_power_wall_policy_auto_climate
  on hc.power_wall_policy (auto_climate, last_action_at);

create index if not exists ix_power_wall_policy_scheduler
  on hc.power_wall_policy (scheduler_enabled, updated_at);

create index if not exists ix_power_wall_schedule_session_entity_status
  on hc.power_wall_schedule_session (entity_id, status, planned_start_at desc);
"""
