alter table hc.power_wall_policy
  add column if not exists auto_climate_delay_minutes integer not null default 0
    check (auto_climate_delay_minutes between 0 and 120);
alter table hc.power_wall_policy
  add column if not exists auto_climate_on_at timestamptz;
