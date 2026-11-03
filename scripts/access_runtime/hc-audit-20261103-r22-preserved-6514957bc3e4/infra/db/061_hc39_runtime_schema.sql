-- HC-39: former lazy DDL, explicit admin-only migration; no worker import.
-- power_wall
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
  add column if not exists auto_climate_delay_minutes integer not null default 0
    check (auto_climate_delay_minutes between 0 and 120);
alter table hc.power_wall_policy
  add column if not exists auto_climate_on_at timestamptz;

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

-- temperature
create table if not exists hc.temperature_sensor_policy (
                  entity_id bigint primary key references hc.entity(id) on delete cascade,
                  is_outdoor boolean not null default false,
                  updated_at timestamptz not null default now()
                );

                alter table hc.temperature_sensor_policy
                  add column if not exists is_outdoor boolean not null default false;

-- opening
create table if not exists hc.opening_sensor_policy (
                  entity_id bigint primary key references hc.entity(id) on delete cascade,
                  opening_type text not null default 'window' check (opening_type in ('window', 'door')),
                  room_position integer,
                  opening_label text,
                  has_mosquito_net boolean not null default false,
                  rain_alert_enabled boolean not null default false,
                  climate_relevant boolean not null default false,
                  extractor_air_role text not null default 'none',
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
                alter table hc.opening_sensor_policy
                  add column if not exists climate_relevant boolean not null default false;
                alter table hc.opening_sensor_policy
                  add column if not exists extractor_air_role text not null default 'none';

-- bindings
create table if not exists hc.process_sensor_binding (
  process_key text primary key,
  entity_id bigint references hc.entity(id) on delete set null,
  updated_at timestamptz not null default now()
);

create index if not exists ix_process_sensor_binding_entity
  on hc.process_sensor_binding (entity_id);

-- page_usage
create table if not exists hc.page_usage_event (
                    id bigserial primary key,
                    created_at timestamptz not null default now(),
                    page_id text not null,
                    client_id text not null,
                    device_class text not null,
                    viewport_width integer,
                    viewport_height integer,
                    standalone boolean not null default false,
                    user_agent text
                );
                create index if not exists ix_page_usage_event_created_at on hc.page_usage_event (created_at desc);
                create index if not exists ix_page_usage_event_page_device on hc.page_usage_event (page_id, device_class, created_at desc);
                create index if not exists ix_page_usage_event_client on hc.page_usage_event (client_id, created_at desc);

-- ai_audit
create table if not exists hc.ai_chat_audit (
                    id bigserial primary key,
                    created_at timestamptz not null default now(),
                    started_at timestamptz,
                    question text not null,
                    answer text,
                    provider text,
                    model text,
                    status_code integer,
                    ok boolean,
                    error text,
                    source text,
                    total_ms numeric,
                    context_ms numeric,
                    knowledge_ms numeric,
                    model_ms numeric,
                    db_query_count integer,
                    skills jsonb not null default '[]'::jsonb,
                    data_sources jsonb not null default '[]'::jsonb,
                    skill_timings jsonb not null default '[]'::jsonb,
                    context_timings jsonb not null default '[]'::jsonb,
                    upstream jsonb not null default '{}'::jsonb,
                    request_meta jsonb not null default '{}'::jsonb
                );
                create index if not exists ix_ai_chat_audit_created_at on hc.ai_chat_audit (created_at desc);
                create index if not exists ix_ai_chat_audit_skills on hc.ai_chat_audit using gin (skills);
                create index if not exists ix_ai_chat_audit_data_sources on hc.ai_chat_audit using gin (data_sources);

-- summaries
create table if not exists hc.irrigation_daily_energy_summary (
                  day date primary key,
                  current_samples bigint,
                  avg_current_a numeric,
                  max_current_a numeric,
                  measured_hours numeric,
                  active_minutes numeric,
                  amp_hours numeric,
                  voltage_samples bigint,
                  avg_voltage_v numeric,
                  watt_hours numeric,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_pump_daily_summary (
                  day date primary key,
                  pump_running_minutes numeric,
                  measured_hours numeric,
                  state_samples bigint,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_solar_daily_summary (
                  day date primary key,
                  avg_battery_voltage_v numeric,
                  min_battery_voltage_v numeric,
                  max_battery_voltage_v numeric,
                  avg_charge_current_a numeric,
                  max_charge_current_a numeric,
                  avg_pv_voltage_v numeric,
                  max_pv_voltage_v numeric,
                  avg_pv_current_a numeric,
                  max_pv_current_a numeric,
                  avg_solar_controller_temp_c numeric,
                  max_solar_controller_temp_c numeric,
                  samples bigint,
                  charge_amp_hours numeric,
                  measured_hours numeric,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_tank_daily_summary (
                  day date primary key,
                  avg_level_percent numeric,
                  min_level_percent numeric,
                  max_level_percent numeric,
                  avg_depth_m numeric,
                  refreshed_at timestamptz not null default now()
                );

                create table if not exists hc.irrigation_controller_temp_daily_summary (
                  day date primary key,
                  avg_controller_temp_c numeric,
                  min_controller_temp_c numeric,
                  max_controller_temp_c numeric,
                  samples bigint,
                  refreshed_at timestamptz not null default now()
                );

-- mower_parameters
-- HC-local RCP1 drafts only. Revision is not a native rover configuration revision.
CREATE TABLE IF NOT EXISTS hc.mower_parameter_revision (
    rover_key text NOT NULL CHECK (rover_key ~ '^[A-Za-z0-9_-]{1,32}$'),
    revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 4294967295),
    expected_revision bigint NOT NULL CHECK (expected_revision = revision - 1),
    request_id text NOT NULL CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    draft_sha256 text NOT NULL CHECK (draft_sha256 ~ '^[0-9a-f]{64}$'),
    saved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rover_key, revision),
    UNIQUE (rover_key, request_id)
);

-- mower_staging
-- HC-local retained firmware only. HC_STAGED is NOT a native update session.
CREATE TABLE IF NOT EXISTS hc.mower_firmware_artifact (
    artifact_id text PRIMARY KEY CHECK (artifact_id ~ '^[0-9a-f]{64}$'),
    image bytea NOT NULL CHECK (octet_length(image) BETWEEN 1280 AND 524288 AND octet_length(image) % 32 = 0),
    elf bytea NOT NULL CHECK (octet_length(elf) BETWEEN 52 AND 16777216),
    saved_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hc.mower_firmware_job (
    hc_job_id text PRIMARY KEY CHECK (hc_job_id ~ '^[0-9A-F]{32}$' AND hc_job_id <> repeat('0', 32)),
    request_id text NOT NULL UNIQUE CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    artifact_id text NOT NULL REFERENCES hc.mower_firmware_artifact(artifact_id),
    release_id text NOT NULL CHECK (release_id ~ '^[A-Za-z0-9_.-]{1,64}$'),
    state text NOT NULL CHECK (state = 'HC_STAGED'),
    report jsonb NOT NULL CHECK (jsonb_typeof(report) = 'object'),
    saved_at timestamptz NOT NULL DEFAULT now()
);

-- mower_sessions
-- Durable single-send create intent. Active UNKNOWN is not cleared by observation.
CREATE TABLE IF NOT EXISTS hc.mower_firmware_session (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    hc_job_id text NOT NULL REFERENCES hc.mower_firmware_job(hc_job_id),
    connection_key text NOT NULL CHECK (connection_key ~ '^[0-9a-f]{64}$'),
    esp_boot text NOT NULL CHECK (esp_boot ~ '^[0-9A-F]{16}$' AND esp_boot <> repeat('0', 16)),
    profile_crc text NOT NULL CHECK (profile_crc ~ '^[0-9A-F]{8}$' AND profile_crc <> '00000000'),
    state text NOT NULL CHECK (state IN ('CREATE_INTENT', 'UNKNOWN', 'ADMITTED', 'REJECTED')),
    update_id text UNIQUE CHECK (update_id ~ '^[0-9A-F]{32}$' AND update_id <> repeat('0', 32)),
    code text NOT NULL CHECK (code ~ '^[A-Z_0-9]{1,32}$'),
    revision integer NOT NULL CHECK (revision BETWEEN 1 AND 2),
    active boolean NOT NULL CHECK (active = (state <> 'REJECTED')),
    singleton boolean NOT NULL DEFAULT true CHECK (singleton),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'ADMITTED') = (update_id IS NOT NULL)),
    CHECK ((state = 'CREATE_INTENT') = (revision = 1))
);
CREATE UNIQUE INDEX IF NOT EXISTS mower_firmware_one_active_session
    ON hc.mower_firmware_session(singleton) WHERE active;

-- mower_operations
-- One durable send intent per native session/action; explicit verified HC exit.
ALTER TABLE hc.mower_firmware_session ADD COLUMN IF NOT EXISTS closed boolean NOT NULL DEFAULT false;
ALTER TABLE hc.mower_firmware_session ADD COLUMN IF NOT EXISTS initial_stm_boot text
    CHECK (initial_stm_boot ~ '^[0-9A-F]{16}$' AND initial_stm_boot <> repeat('0', 16));
ALTER TABLE hc.mower_firmware_session DROP CONSTRAINT IF EXISTS mower_firmware_session_active_check;
-- Migration 054's cross-column inline CHECK receives this PostgreSQL name.
ALTER TABLE hc.mower_firmware_session DROP CONSTRAINT IF EXISTS mower_firmware_session_check;
ALTER TABLE hc.mower_firmware_session ADD CONSTRAINT mower_firmware_session_active_check
    CHECK (active = (state <> 'REJECTED' AND NOT closed));
CREATE TABLE IF NOT EXISTS hc.mower_firmware_operation (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    session_request_id text NOT NULL REFERENCES hc.mower_firmware_session(request_id),
    action text NOT NULL CHECK (action IN ('IMAGE', 'ABORT', 'FINISH')),
    state text NOT NULL CHECK (state IN ('INTENT', 'UNKNOWN', 'ADMITTED', 'REJECTED')),
    code text NOT NULL CHECK (code ~ '^[A-Z_0-9]{1,32}$'),
    service_boot text NOT NULL CHECK (service_boot ~ '^[0-9A-F]{16}$' AND service_boot <> repeat('0', 16)),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_request_id, action)
);
CREATE TABLE IF NOT EXISTS hc.mower_firmware_exit (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    session_request_id text NOT NULL UNIQUE REFERENCES hc.mower_firmware_session(request_id),
    proof jsonb NOT NULL CHECK (jsonb_typeof(proof) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- climate_window
create table if not exists hc.climate_window_guard (
 id integer primary key check(id=1),
 open_delay_seconds integer not null default 60,
 close_delay_seconds integer not null default 60,
 desired jsonb not null default '{}',
 suspended boolean not null default false
);
insert into hc.climate_window_guard(id) values(1) on conflict do nothing;
