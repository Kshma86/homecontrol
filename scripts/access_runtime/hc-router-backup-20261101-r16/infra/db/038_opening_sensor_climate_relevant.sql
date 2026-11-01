begin;

alter table hc.opening_sensor_policy
  add column if not exists climate_relevant boolean not null default false;

commit;
