begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('climate_ok', 'bool', null, null, null, 'Gree climate bridge state ok flag', false, true),
  ('climate_power', 'text', null, null, null, 'Gree climate power setting', false, true),
  ('climate_mode', 'text', null, null, null, 'Gree climate operating mode', false, true),
  ('climate_target_temperature', 'num', 'C', 8, 30, 'Gree climate target temperature', true, true),
  ('climate_current_temperature', 'num', 'C', -40, 80, 'Gree climate reported current temperature', true, true),
  ('climate_fan_speed', 'text', null, null, null, 'Gree climate fan speed setting', false, true),
  ('climate_error', 'text', null, null, null, 'Gree climate bridge error text', false, true),
  ('climate_command_result', 'json', null, null, null, 'Gree climate command result payload', false, true)
on conflict (key) do update set
  value_type = excluded.value_type,
  unit = excluded.unit,
  min_num = excluded.min_num,
  max_num = excluded.max_num,
  description = excluded.description,
  enforce_validation = excluded.enforce_validation,
  is_active = true;

with device_upsert as (
  insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
  values ('wifi', 'gree_climate_9424b8ba43f7', 'Gree klíma', 'Klíma', 'Split AC', 'Gree', true)
  on conflict (platform, ext_id) do update set
    name = excluded.name,
    location = excluded.location,
    model = excluded.model,
    manufacturer = excluded.manufacturer,
    is_active = true,
    updated_at = now()
  returning id
)
insert into hc.entity (device_id, name, topic_base, is_active)
select id, 'Gree klíma', 'homecontrol/gree_climate', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('climate_ok', 'both', null::double precision, 30, 300),
  ('climate_power', 'both', null::double precision, 30, 900),
  ('climate_mode', 'both', null::double precision, 30, 900),
  ('climate_target_temperature', 'both', null::double precision, 30, 900),
  ('climate_current_temperature', 'both', 0.2::double precision, 60, 900),
  ('climate_fan_speed', 'both', null::double precision, 30, 900),
  ('climate_error', 'state', null::double precision, 30, 300),
  ('climate_command_result', 'state', null::double precision, 5, 300)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'wifi'
  and d.ext_id = 'gree_climate_9424b8ba43f7'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

update hc.entity_metric em
set is_enabled = false
from hc.entity e
join hc.device d on d.id = e.device_id
where em.entity_id = e.id
  and e.topic_base = 'homecontrol/gree_climate'
  and em.metric_key in ('climate_state', 'climate_current_humidity', 'climate_target_humidity', 'climate_light');

commit;
