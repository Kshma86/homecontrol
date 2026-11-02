begin;

alter table hc.opening_sensor_policy
  add column if not exists room_position integer;
alter table hc.opening_sensor_policy
  add column if not exists opening_label text;
alter table hc.opening_sensor_policy
  add column if not exists has_mosquito_net boolean not null default false;

commit;
