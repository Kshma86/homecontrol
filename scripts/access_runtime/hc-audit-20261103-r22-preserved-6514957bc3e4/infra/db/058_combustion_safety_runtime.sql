-- HC-06: additive runtime state; never rewrite business configuration.
begin;
create table if not exists hc.combustion_safety_runtime (
  singleton boolean primary key default true check (singleton),
  revision bigint not null default 0,
  latched boolean not null default true,
  co_warning_active boolean not null default false,
  last_co double precision,
  last_co_sample_at timestamptz,
  updated_at timestamptz not null default now(),
  acknowledged_at timestamptz
);
-- First installation has no trustworthy pre-restart latch record. Require
-- explicit acknowledgement with fresh clear inputs, rather than assume clear.
insert into hc.combustion_safety_runtime(singleton) values(true)
on conflict(singleton) do nothing;
commit;
