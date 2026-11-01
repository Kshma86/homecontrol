begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('temperature', 'num', 'C', -40, 80, 'Temperature reported by room sensors', true, true),
  ('humidity', 'num', '%', 0, 100, 'Relative humidity reported by room sensors', true, true),
  ('pressure_hpa', 'num', 'hPa', 800, 1200, 'Atmospheric pressure reported by local sensors or weather providers', true, true),
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

with sensor_seed(ext_id, entity_name, device_name, location, model, manufacturer, is_outdoor) as (
  values
    ('0x00158d008c834096', 'Udvar', 'Udvar', 'Udvar', 'Temperature/humidity/pressure sensor', 'Zigbee', true),
    ('0xa4c13893c7ea4324', 'Nyárikonyha', 'Nyárikonyha', 'Nyárikonyha', 'Temperature/humidity sensor', 'Zigbee', false)
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
),
updated_entity as (
  update hc.entity e
  set name = s.entity_name,
      topic_base = 'zigbee/' || s.ext_id,
      is_active = true
  from device_rows d
  join sensor_seed s on s.ext_id = d.ext_id
  where e.device_id = d.id
  returning e.id, s.ext_id
),
inserted_entity as (
  insert into hc.entity (device_id, name, topic_base, is_active)
  select d.id, s.entity_name, 'zigbee/' || s.ext_id, true
  from device_rows d
  join sensor_seed s on s.ext_id = d.ext_id
  where not exists (select 1 from updated_entity ue where ue.ext_id = s.ext_id)
  on conflict (device_id, name) do update set
    topic_base = excluded.topic_base,
    is_active = true
  returning id
),
target_entity as (
  select id from updated_entity
  union all
  select id from inserted_entity
)
insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from target_entity e
join (values
  ('temperature', 'both', 0.1::double precision, 30, 600),
  ('humidity', 'both', 1::double precision, 30, 600),
  ('battery', 'both', 1::double precision, 300, 21600),
  ('linkquality', 'state', 1::double precision, 60, 600)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, 'pressure_hpa', 'both', 0.2::double precision, 30, 600, true
from hc.entity e
join hc.device d on d.id = e.device_id
where d.platform = 'zigbee'
  and d.ext_id = '0x00158d008c834096'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

insert into hc.temperature_sensor_policy (entity_id, is_outdoor, updated_at)
select e.id, s.is_outdoor, now()
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('0x00158d008c834096', true),
  ('0xa4c13893c7ea4324', false)
) as s(ext_id, is_outdoor) on s.ext_id = d.ext_id
where d.platform = 'zigbee'
  and d.ext_id in ('0x00158d008c834096', '0xa4c13893c7ea4324')
on conflict (entity_id) do update set
  is_outdoor = excluded.is_outdoor,
  updated_at = now();

delete from hc.opening_sensor_policy osp
using hc.entity e
join hc.device d on d.id = e.device_id
where osp.entity_id = e.id
  and d.platform = 'zigbee'
  and d.ext_id in ('0x00158d008c834096', '0xa4c13893c7ea4324');

commit;
