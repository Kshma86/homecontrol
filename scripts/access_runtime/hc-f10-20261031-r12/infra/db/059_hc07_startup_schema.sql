-- HC-07: explicit, transactional migration. No inventory/mode/schedule rewrite.
create table if not exists hc.irrigation_pilot_config (
  id smallint primary key default 1 check (id = 1),
  mode text not null default 'navigator' check (mode in ('navigator', 'pilot')),
  base_duration_minutes integer not null default 90 check (base_duration_minutes between 1 and 720),
  rain_24h_threshold_mm numeric not null default 5,
  forecast_rain_threshold_mm numeric not null default 5,
  pop_threshold_percent integer not null default 70 check (pop_threshold_percent between 0 and 100),
  heat_threshold_c numeric not null default 32,
  heat_correction_percent integer not null default 20,
  heat_step_c numeric not null default 5,
  heat_multiplier_step numeric not null default 0.1,
  cold_threshold_c numeric not null default 22,
  cold_correction_percent integer not null default -20,
  cold_step_c numeric not null default 5,
  cold_multiplier_step numeric not null default -0.1,
  soil_moisture_enabled boolean not null default true,
  soil_sensor_topic_base text not null default 'zigbee/0xa4c13844a0908898',
  soil_wet_skip_threshold_percent numeric not null default 85,
  soil_wet_adjust_threshold_percent numeric not null default 65,
  soil_wet_multiplier_delta numeric not null default -0.5,
  soil_dry_threshold_percent numeric not null default 45,
  soil_dry_correction_percent integer not null default 15,
  soil_dry_multiplier_delta numeric not null default 0.15,
  soil_sample_max_age_hours integer not null default 12,
  min_duration_multiplier numeric not null default 0.2,
  max_duration_multiplier numeric not null default 1.5,
  updated_at timestamptz not null default now()
);

alter table hc.irrigation_pilot_config
  add column if not exists heat_step_c numeric not null default 5,
  add column if not exists heat_multiplier_step numeric not null default 0.1,
  add column if not exists cold_step_c numeric not null default 5,
  add column if not exists cold_multiplier_step numeric not null default -0.1,
  add column if not exists soil_moisture_enabled boolean not null default true,
  add column if not exists soil_sensor_topic_base text not null default 'zigbee/0xa4c13844a0908898',
  add column if not exists soil_wet_skip_threshold_percent numeric not null default 85,
  add column if not exists soil_wet_adjust_threshold_percent numeric not null default 65,
  add column if not exists soil_wet_multiplier_delta numeric not null default -0.5,
  add column if not exists soil_dry_threshold_percent numeric not null default 45,
  add column if not exists soil_dry_correction_percent integer not null default 15,
  add column if not exists soil_dry_multiplier_delta numeric not null default 0.15,
  add column if not exists soil_sample_max_age_hours integer not null default 12,
  add column if not exists min_duration_multiplier numeric not null default 0.2,
  add column if not exists max_duration_multiplier numeric not null default 1.5;



create table if not exists hc.irrigation_solar_pump_config (
  id smallint primary key default 1 check (id = 1),
  enabled boolean not null default false,
  daily_target_minutes integer not null default 30 check (daily_target_minutes between 1 and 240),
  batch_minutes integer not null default 5 check (batch_minutes between 1 and 60),
  cooldown_minutes integer not null default 10 check (cooldown_minutes between 0 and 240),
  min_charge_current_a numeric not null default 0.8,
  min_pv_voltage_v numeric not null default 15,
  min_battery_voltage_v numeric not null default 12.2,
  stop_battery_voltage_v numeric not null default 11.8,
  max_telemetry_age_seconds integer not null default 180 check (max_telemetry_age_seconds between 10 and 3600),
  require_remote_mode boolean not null default true,
  latest_decision jsonb,
  updated_at timestamptz not null default now()
);

alter table hc.irrigation_solar_pump_config
  add column if not exists enabled boolean not null default false,
  add column if not exists daily_target_minutes integer not null default 30,
  add column if not exists batch_minutes integer not null default 5,
  add column if not exists cooldown_minutes integer not null default 10,
  add column if not exists min_charge_current_a numeric not null default 0.8,
  add column if not exists min_pv_voltage_v numeric not null default 15,
  add column if not exists min_battery_voltage_v numeric not null default 12.2,
  add column if not exists stop_battery_voltage_v numeric not null default 11.8,
  add column if not exists max_telemetry_age_seconds integer not null default 180,
  add column if not exists require_remote_mode boolean not null default true,
  add column if not exists latest_decision jsonb,
  add column if not exists updated_at timestamptz not null default now();



create table if not exists hc.irrigation_solar_pump_run (
  id bigserial primary key,
  started_at timestamptz not null default now(),
  planned_stop_at timestamptz not null,
  stopped_at timestamptz,
  status text not null default 'running',
  start_payload jsonb,
  stop_payload jsonb,
  error text
);

create index if not exists irrigation_solar_pump_run_started_idx
  on hc.irrigation_solar_pump_run (started_at desc);

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

create table if not exists hc.scheduler_config (
  id smallint primary key default 1 check (id = 1),
  mode text not null default 'v2_execute_all' check (mode in ('v2_execute_irrigation', 'v2_execute_x10', 'v2_execute_climate', 'v2_execute_x10_climate', 'v2_execute_all')),
  updated_at timestamptz not null default now(),
  updated_by text not null default 'system',
  notes text
);



alter table hc.scheduler_config drop constraint if exists scheduler_config_mode_check;
alter table hc.scheduler_config alter column mode set default 'v2_execute_all';
alter table hc.scheduler_config add constraint scheduler_config_mode_check
  check (mode in ('legacy','v2_shadow','v2_plan_only','unified_shadow','v2_execute_irrigation','v2_execute_x10','v2_execute_climate','v2_execute_x10_climate','v2_execute_all'));




create table if not exists hc.scheduler_job (
  id bigserial primary key,
  domain text not null,
  action text not null,
  label text not null,
  schedule_kind text not null default 'weekly',
  day_of_week smallint check (day_of_week between 0 and 6),
  start_time time,
  stop_time time,
  is_enabled boolean not null default false,
  source text not null default 'unified',
  source_ref text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (domain, source, source_ref)
);

create table if not exists hc.scheduler_run (
  id bigserial primary key,
  job_id bigint references hc.scheduler_job(id) on delete set null,
  domain text not null,
  action text not null,
  status text not null default 'pending',
  attempt integer not null default 0,
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  confirmed_started_at timestamptz,
  stop_requested_at timestamptz,
  confirmed_stopped_at timestamptz,
  completed_at timestamptz,
  error text,
  payload jsonb not null default '{}'::jsonb,
  confirmation jsonb not null default '{}'::jsonb
);

alter table hc.scheduler_run
  add column if not exists idempotency_key text;

create index if not exists ix_scheduler_job_due
  on hc.scheduler_job (is_enabled, day_of_week, start_time);

create index if not exists ix_scheduler_run_requested
  on hc.scheduler_run (requested_at desc);

create unique index if not exists ux_scheduler_run_idempotency
  on hc.scheduler_run (idempotency_key)
  where idempotency_key is not null;

create table if not exists hc.climate_schedule_rule (
  id bigserial primary key,
  label text not null,
  day_of_week smallint check (day_of_week between 0 and 6),
  start_time time not null,
  is_enabled boolean not null default false,
  power text not null default 'on' check (power in ('keep', 'on', 'off')),
  mode text not null default 'heat' check (mode in ('keep', 'auto', 'cool', 'dry', 'fan', 'heat')),
  target_temperature integer not null default 23 check (target_temperature between 8 and 30),
  fan_speed text not null default 'auto' check (fan_speed in ('keep', 'auto', 'low', 'mediumlow', 'medium', 'mediumhigh', 'high', 'quiet', 'turbo')),
  light text not null default 'off' check (light in ('keep', 'on', 'off')),
  extra_fan text not null default 'keep' check (extra_fan in ('keep', 'on', 'off')),
  rule_engine jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_label_day_of_week_start_time_key;

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_fan_speed_check;

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_power_check;

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_mode_check;

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_light_check;

alter table hc.climate_schedule_rule
  add constraint climate_schedule_rule_fan_speed_check
  check (fan_speed in ('keep', 'auto', 'low', 'mediumlow', 'medium', 'mediumhigh', 'high', 'quiet', 'turbo'));

alter table hc.climate_schedule_rule
  add constraint climate_schedule_rule_power_check
  check (power in ('keep', 'on', 'off'));

alter table hc.climate_schedule_rule
  add constraint climate_schedule_rule_mode_check
  check (mode in ('keep', 'auto', 'cool', 'dry', 'fan', 'heat'));

alter table hc.climate_schedule_rule
  add constraint climate_schedule_rule_light_check
  check (light in ('keep', 'on', 'off'));

alter table hc.climate_schedule_rule
  add column if not exists extra_fan text not null default 'keep';

alter table hc.climate_schedule_rule
  add column if not exists season_profile text not null default 'summer';

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_season_profile_check;

alter table hc.climate_schedule_rule
  add constraint climate_schedule_rule_season_profile_check
  check (season_profile in ('summer', 'winter'));

alter table hc.climate_schedule_rule
  drop constraint if exists climate_schedule_rule_extra_fan_check;

alter table hc.climate_schedule_rule
  add constraint climate_schedule_rule_extra_fan_check
  check (extra_fan in ('keep', 'on', 'off'));

drop index if exists hc.ux_climate_schedule_rule_day;

create index if not exists ix_climate_schedule_rule_day_time
  on hc.climate_schedule_rule (day_of_week, start_time);

create index if not exists ix_climate_schedule_rule_profile_day_time
  on hc.climate_schedule_rule (season_profile, day_of_week, start_time);

create table if not exists hc.domain_season_profile (
  domain text not null check (domain in ('irrigation', 'climate')),
  profile text not null check (profile in ('summer', 'winter')),
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (domain, profile)
);

create table if not exists hc.domain_season_active (
  domain text primary key check (domain in ('irrigation', 'climate')),
  profile text not null check (profile in ('summer', 'winter')),
  activated_at timestamptz not null default now()
);


create table if not exists hc.notes (
  id bigserial primary key,
  type text not null check (type in ('issues', 'requests')),
  text text not null check (length(trim(text)) > 0),
  comment text not null default '',
  done boolean not null default false,
  status text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table hc.notes
  add column if not exists comment text not null default '';
alter table hc.notes
  add column if not exists status text;
alter table hc.notes
  add column if not exists scope text not null default 'general';



create index if not exists ix_notes_type_done_created_at
  on hc.notes (type, done, created_at desc);

create index if not exists ix_notes_created_at
  on hc.notes (created_at desc);
create index if not exists ix_notes_scope_status_created_at
  on hc.notes (scope, status, created_at desc);
