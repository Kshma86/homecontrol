begin;

alter table hc.opening_sensor_policy
  add column if not exists rain_alert_enabled boolean not null default false;

commit;
