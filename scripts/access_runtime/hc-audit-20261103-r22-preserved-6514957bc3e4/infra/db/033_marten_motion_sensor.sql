begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('occupancy', 'bool', null, null, null, 'PIR occupancy or motion state from Zigbee sensors', false, true),
  ('motion', 'bool', null, null, null, 'PIR motion state from Zigbee sensors', false, true),
  ('presence', 'bool', null, null, null, 'Presence state from Zigbee sensors', false, true),
  ('battery_low', 'bool', null, null, null, 'Battery low flag', false, true),
  ('battery', 'num', '%', 0, 100, 'Battery percent', true, true),
  ('linkquality', 'num', null, 0, 255, 'Zigbee link quality', true, true)
on conflict (key) do update set
  value_type = excluded.value_type,
  unit = excluded.unit,
  min_num = excluded.min_num,
  max_num = excluded.max_num,
  description = excluded.description,
  enforce_validation = excluded.enforce_validation,
  is_active = true;

with sensor_seed(ext_id, entity_name, device_name, location, model, manufacturer) as (
  values ('0xa4c1386aa4a76dd5', 'Nyestriasztó PIR', 'Nyestriasztó PIR', 'Kültér', 'PIR motion sensor', 'Tuya')
),
device_rows as (
  insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
  select 'zigbee', ext_id, device_name, location, model, manufacturer, true
  from sensor_seed
  on conflict (platform, ext_id) do update set
    name = excluded.name,
    location = excluded.location,
    model = excluded.model,
    manufacturer = excluded.manufacturer,
    is_active = true,
    updated_at = now()
  returning id, ext_id
)
insert into hc.entity (device_id, name, topic_base, is_active)
select d.id, s.entity_name, 'zigbee/' || s.ext_id, true
from device_rows d
join sensor_seed s on s.ext_id = d.ext_id
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('occupancy', 'both', null::double precision, 1, 86400),
  ('motion', 'both', null::double precision, 1, 86400),
  ('presence', 'both', null::double precision, 1, 86400),
  ('battery_low', 'both', null::double precision, 1, 86400),
  ('battery', 'both', 1::double precision, 3600, 86400),
  ('linkquality', 'state', 1::double precision, 60, 600)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'zigbee'
  and d.ext_id = '0xa4c1386aa4a76dd5'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'marten_motion_sensor', e.id, now()
from hc.entity e
where e.topic_base = 'zigbee/0xa4c1386aa4a76dd5'
on conflict (process_key) do nothing;

commit;
