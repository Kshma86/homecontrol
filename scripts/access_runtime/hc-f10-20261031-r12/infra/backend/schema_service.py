from runtime_schema_contract import check_runtime_schema
from threading import Lock
from typing import Callable

from startup_schema_contract import check_domain


class HcSchemaService:
    def __init__(self, execute_sql: Callable[[str], None], fetch_one=None):
        self.execute_sql = execute_sql
        self.fetch_one = fetch_one
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
            check_domain(self.fetch_one, "pilot")
            self._pilot_ready = True

    def ensure_power_wall_schema(self) -> None:
        if self._power_wall_ready:
            return
        with self._power_wall_lock:
            if self._power_wall_ready:
                return
            check_runtime_schema(self.execute_sql, "power_wall")
            self._power_wall_ready = True


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
"""
