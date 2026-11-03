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

create index if not exists ix_power_wall_policy_scheduler
  on hc.power_wall_policy (scheduler_enabled, updated_at);

create index if not exists ix_power_wall_schedule_session_entity_status
  on hc.power_wall_schedule_session (entity_id, status, planned_start_at desc);
