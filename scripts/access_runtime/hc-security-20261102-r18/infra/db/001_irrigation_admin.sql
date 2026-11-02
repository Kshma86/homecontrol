begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('liquid_level_percent', 'num', '%', 0, 100, 'Tank liquid level percent', true, true),
  ('liquid_depth', 'num', 'm', 0, 10, 'Tank liquid depth', true, true),
  ('liquid_state', 'text', null, null, null, 'Tank liquid state', false, true),
  ('pump_running', 'bool', null, null, null, 'Irrigation pump running state', false, true),
  ('pump_current_a', 'num', 'A', 0, 50, 'Irrigation pump current', true, true),
  ('supply_voltage_12v', 'num', 'V', 0, 20, 'Irrigation 12V supply voltage', true, true),
  ('controller_temp_c', 'num', 'C', -40, 100, 'Irrigation controller temperature', true, true),
  ('valve_state', 'text', null, null, null, 'Irrigation valve state', false, true),
  ('valve_code', 'num', null, 0, 9999, 'Irrigation valve numeric code', true, true),
  ('valve_code_text', 'text', null, null, null, 'Irrigation valve code text', false, true),
  ('valve_current_a', 'num', 'A', 0, 20, 'Irrigation valve current', true, true),
  ('manual_valve_state', 'text', null, null, null, 'Manual valve state', false, true),
  ('solar_battery_voltage_v', 'num', 'V', 0, 20, 'Solar battery voltage', true, true),
  ('solar_charge_current_a', 'num', 'A', 0, 50, 'Solar battery charge current', true, true),
  ('solar_pv_voltage_v', 'num', 'V', 0, 60, 'Solar panel voltage', true, true),
  ('solar_pv_current_a', 'num', 'A', 0, 50, 'Solar panel current', true, true),
  ('solar_controller_temp_c', 'num', 'C', -40, 120, 'Solar controller temperature', true, true),
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

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join (values
  ('liquid_level_percent', 'both', 1::double precision, 30, 300),
  ('liquid_depth', 'both', 0.01::double precision, 30, 300),
  ('liquid_state', 'both', null::double precision, 30, 300),
  ('linkquality', 'both', null::double precision, 3600, 3600)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where e.topic_base = 'zigbee/0xa4c13880b130079c'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

with device_upsert as (
  insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
  values ('wifi', 'esp-irrigation-1', 'Irrigation controller', 'Kert', 'ESP irrigation', 'HomeControl', true)
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
select id, 'Irrigation controller', 'homecontrol/tele/irrigation/esp-irrigation-1', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('pump_running', 'both', null::double precision, 1, 60),
  ('pump_current_a', 'both', 0.05::double precision, 5, 60),
  ('supply_voltage_12v', 'both', 0.05::double precision, 30, 300),
  ('controller_temp_c', 'both', 0.2::double precision, 30, 300),
  ('valve_state', 'both', null::double precision, 1, 60),
  ('valve_code', 'both', null::double precision, 1, 60),
  ('valve_code_text', 'both', null::double precision, 1, 60),
  ('valve_current_a', 'both', 0.02::double precision, 5, 60),
  ('manual_valve_state', 'both', null::double precision, 1, 60),
  ('solar_battery_voltage_v', 'both', 0.05::double precision, 30, 300),
  ('solar_charge_current_a', 'both', 0.05::double precision, 30, 300),
  ('solar_pv_voltage_v', 'both', 0.1::double precision, 30, 300),
  ('solar_pv_current_a', 'both', 0.05::double precision, 30, 300),
  ('solar_controller_temp_c', 'both', 0.5::double precision, 30, 300),
  ('linkquality', 'both', null::double precision, 3600, 3600)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'wifi' and d.ext_id = 'esp-irrigation-1'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

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

create table if not exists hc.irrigation_manual_session (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  started_at timestamptz not null default now(),
  requested_stop_at timestamptz not null,
  safety_stop_at timestamptz not null,
  stopped_at timestamptz,
  status text not null default 'running',
  started_by text not null default 'admin',
  start_payload jsonb not null default '{}'::jsonb,
  stop_payload jsonb,
  error text
);

create index if not exists ix_irrigation_manual_session_status_stop
  on hc.irrigation_manual_session (status, requested_stop_at);

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

create table if not exists hc.irrigation_schedule (
  id bigserial primary key,
  day_of_week smallint not null check (day_of_week between 0 and 6),
  label text not null,
  start_time time not null default '06:00',
  stop_time time not null default '06:20',
  is_active boolean not null default false,
  last_started_on date,
  last_stopped_on date,
  updated_at timestamptz not null default now(),
  check (start_time < stop_time)
);

insert into hc.irrigation_schedule (day_of_week, label, start_time, stop_time, is_active)
select day_of_week, label, start_time::time, stop_time::time, is_active
from (values
  (0, 'Monday', '06:00', '06:20', false),
  (1, 'Tuesday', '06:00', '06:20', false),
  (2, 'Wednesday', '06:00', '06:20', false),
  (3, 'Thursday', '06:00', '06:20', false),
  (4, 'Friday', '06:00', '06:20', false),
  (5, 'Saturday', '06:00', '06:20', false),
  (6, 'Sunday', '06:00', '06:20', false)
) as defaults(day_of_week, label, start_time, stop_time, is_active)
where not exists (
  select 1 from hc.irrigation_schedule existing
  where existing.day_of_week = defaults.day_of_week
);

create index if not exists ix_irrigation_schedule_day_start
  on hc.irrigation_schedule (day_of_week, start_time, id);

drop view if exists hc.irrigation_daily_energy;

create view hc.irrigation_daily_energy as
with current_samples as (
  select
    ts,
    greatest(v_num, 0) as current_a,
    lead(ts) over (order by ts) as next_ts
  from hc.measurement
  where key = 'pump_current_a'
),
current_intervals as (
  select
    ts as start_ts,
    least(coalesce(next_ts, ts), ts + interval '5 minutes') as end_ts,
    current_a
  from current_samples
),
current_by_day as (
  select
    g.day_start::date as day,
    current_a,
    extract(epoch from least(end_ts, g.day_start + interval '1 day') - greatest(start_ts, g.day_start)) as seconds
  from current_intervals
  cross join lateral generate_series(
    date_trunc('day', start_ts),
    date_trunc('day', end_ts),
    interval '1 day'
  ) as g(day_start)
  where end_ts > start_ts
    and least(end_ts, g.day_start + interval '1 day') > greatest(start_ts, g.day_start)
),
daily_current as (
  select
    day,
    count(*) as current_samples,
    round(avg(current_a)::numeric, 3) as avg_current_a,
    round(max(current_a)::numeric, 3) as max_current_a,
    round((sum(seconds) / 3600.0)::numeric, 3) as measured_hours,
    round((sum(case when current_a > 0.05 then seconds else 0 end) / 60.0)::numeric, 1) as active_minutes,
    round((sum(current_a * seconds) / 3600.0)::numeric, 3) as amp_hours
  from current_by_day
  group by day
),
daily_voltage as (
  select
    date_trunc('day', ts)::date as day,
    count(*) as voltage_samples,
    round(avg(v_num)::numeric, 3) as avg_voltage_v
  from hc.measurement
  where key = 'supply_voltage_12v'
  group by date_trunc('day', ts)::date
)
select
  c.day,
  c.current_samples,
  c.avg_current_a,
  c.max_current_a,
  c.measured_hours,
  c.active_minutes,
  c.amp_hours,
  v.voltage_samples,
  v.avg_voltage_v,
  round((c.amp_hours * v.avg_voltage_v)::numeric, 2) as watt_hours
from daily_current c
left join daily_voltage v on v.day = c.day;

create or replace view hc.irrigation_pump_daily as
with samples as (
  select
    ts,
    coalesce(v_bool, false) as pump_running,
    lead(ts) over (order by ts) as next_ts
  from hc.measurement
  where key = 'pump_running'
),
intervals as (
  select
    ts as start_ts,
    least(coalesce(next_ts, ts), ts + interval '5 minutes') as end_ts,
    pump_running
  from samples
),
by_day as (
  select
    g.day_start::date as day,
    pump_running,
    extract(epoch from least(end_ts, g.day_start + interval '1 day') - greatest(start_ts, g.day_start)) as seconds
  from intervals
  cross join lateral generate_series(
    date_trunc('day', start_ts),
    date_trunc('day', end_ts),
    interval '1 day'
  ) as g(day_start)
  where end_ts > start_ts
    and least(end_ts, g.day_start + interval '1 day') > greatest(start_ts, g.day_start)
)
select
  day,
  round((sum(case when pump_running then seconds else 0 end) / 60.0)::numeric, 1) as pump_running_minutes,
  round((sum(seconds) / 3600.0)::numeric, 3) as measured_hours,
  count(*) as state_samples
from by_day
group by day;

create or replace view hc.irrigation_solar_daily as
with charge_samples as (
  select
    ts,
    greatest(v_num, 0) as current_a,
    lead(ts) over (order by ts) as next_ts
  from hc.measurement
  where key = 'solar_charge_current_a'
),
charge_intervals as (
  select
    ts as start_ts,
    least(coalesce(next_ts, ts), ts + interval '5 minutes') as end_ts,
    current_a
  from charge_samples
),
charge_by_day as (
  select
    g.day_start::date as day,
    current_a,
    extract(epoch from least(end_ts, g.day_start + interval '1 day') - greatest(start_ts, g.day_start)) as seconds
  from charge_intervals
  cross join lateral generate_series(
    date_trunc('day', start_ts),
    date_trunc('day', end_ts),
    interval '1 day'
  ) as g(day_start)
  where end_ts > start_ts
    and least(end_ts, g.day_start + interval '1 day') > greatest(start_ts, g.day_start)
),
metric_daily as (
  select
    date_trunc('day', ts)::date as day,
    round(avg(v_num) filter (where key = 'solar_battery_voltage_v')::numeric, 3) as avg_battery_voltage_v,
    round(min(v_num) filter (where key = 'solar_battery_voltage_v')::numeric, 3) as min_battery_voltage_v,
    round(max(v_num) filter (where key = 'solar_battery_voltage_v')::numeric, 3) as max_battery_voltage_v,
    round(avg(v_num) filter (where key = 'solar_charge_current_a')::numeric, 3) as avg_charge_current_a,
    round(max(v_num) filter (where key = 'solar_charge_current_a')::numeric, 3) as max_charge_current_a,
    round(avg(v_num) filter (where key = 'solar_pv_voltage_v')::numeric, 3) as avg_pv_voltage_v,
    round(max(v_num) filter (where key = 'solar_pv_voltage_v')::numeric, 3) as max_pv_voltage_v,
    round(avg(v_num) filter (where key = 'solar_pv_current_a')::numeric, 3) as avg_pv_current_a,
    round(max(v_num) filter (where key = 'solar_pv_current_a')::numeric, 3) as max_pv_current_a,
    round(avg(v_num) filter (where key = 'solar_controller_temp_c')::numeric, 2) as avg_solar_controller_temp_c,
    round(max(v_num) filter (where key = 'solar_controller_temp_c')::numeric, 2) as max_solar_controller_temp_c,
    count(*) as samples
  from hc.measurement
  where key in (
    'solar_battery_voltage_v',
    'solar_charge_current_a',
    'solar_pv_voltage_v',
    'solar_pv_current_a',
    'solar_controller_temp_c'
  )
  group by date_trunc('day', ts)::date
),
charge_daily as (
  select
    day,
    round((sum(current_a * seconds) / 3600.0)::numeric, 3) as charge_amp_hours,
    round((sum(seconds) / 3600.0)::numeric, 3) as measured_hours
  from charge_by_day
  group by day
)
select
  m.*,
  c.charge_amp_hours,
  c.measured_hours
from metric_daily m
left join charge_daily c on c.day = m.day;

create or replace view hc.irrigation_controller_temp_daily as
select
  date_trunc('day', ts)::date as day,
  round(avg(v_num)::numeric, 2) as avg_controller_temp_c,
  round(min(v_num)::numeric, 2) as min_controller_temp_c,
  round(max(v_num)::numeric, 2) as max_controller_temp_c,
  count(*) as samples
from hc.measurement
where key = 'controller_temp_c'
group by date_trunc('day', ts)::date;

create or replace view hc.irrigation_tank_daily as
select
  date_trunc('day', ts)::date as day,
  round(avg(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as avg_level_percent,
  round(min(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as min_level_percent,
  round(max(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as max_level_percent,
  round(avg(v_num) filter (where key = 'liquid_depth')::numeric, 3) as avg_depth_m
from hc.measurement
where key in ('liquid_level_percent', 'liquid_depth')
group by date_trunc('day', ts)::date;

drop view if exists hc.irrigation_session_stats;

create view hc.irrigation_session_stats as
select
  s.id,
  s.started_at,
  s.stopped_at,
  s.status,
  s.started_by,
  s.start_payload ->> 'source' as source,
  nullif(s.start_payload ->> 'schedule_id', '')::bigint as schedule_id,
  s.start_payload ->> 'schedule_label' as schedule_label,
  round((extract(epoch from (coalesce(s.stopped_at, now()) - s.started_at)) / 60.0)::numeric, 1) as duration_minutes
from hc.irrigation_manual_session s;

drop table if exists hc.irrigation_water_calibration;

commit;
