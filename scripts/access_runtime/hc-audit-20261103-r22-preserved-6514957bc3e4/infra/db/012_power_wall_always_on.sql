create table if not exists hc.power_wall_policy (
  entity_id bigint primary key references hc.entity(id) on delete cascade,
  display_name text,
  always_on boolean not null default false,
  last_action_at timestamptz,
  last_action text,
  last_error text,
  updated_at timestamptz not null default now()
);

create index if not exists ix_power_wall_policy_always_on
  on hc.power_wall_policy (always_on, last_action_at);
