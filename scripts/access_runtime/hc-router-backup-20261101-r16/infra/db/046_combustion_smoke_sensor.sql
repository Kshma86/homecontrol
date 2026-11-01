begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('smoke', 'bool', null, null, null, 'Smoke alarm state', false, true),
  ('tamper', 'bool', null, null, null, 'Sensor tamper state', false, true),
  ('trouble', 'bool', null, null, null, 'Sensor trouble state', false, true),
  ('test', 'bool', null, null, null, 'Sensor test state', false, true),
  ('battery_defect', 'bool', null, null, null, 'Sensor battery defect state', false, true)
on conflict (key) do update set
  value_type = excluded.value_type,
  description = excluded.description,
  enforce_validation = excluded.enforce_validation,
  is_active = true;

insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
values (
  'zigbee', '0x403802fffeb11030', 'Füstérzékelő', 'Otthon',
  'SmokeSensor-EF-3.0', 'HEIMAN', true
)
on conflict (platform, ext_id) do update set
  name = excluded.name,
  location = excluded.location,
  model = excluded.model,
  manufacturer = excluded.manufacturer,
  is_active = true,
  updated_at = now();

insert into hc.entity (device_id, name, topic_base, is_active)
select d.id, 'Füstérzékelő', 'zigbee/0x403802fffeb11030', true
from hc.device d
where d.platform = 'zigbee' and d.ext_id = '0x403802fffeb11030'
  and not exists (select 1 from hc.entity e where e.device_id = d.id);

update hc.entity e
set name = 'Füstérzékelő',
    topic_base = 'zigbee/0x403802fffeb11030',
    is_active = true
from hc.device d
where e.device_id = d.id
  and d.platform = 'zigbee'
  and d.ext_id = '0x403802fffeb11030';

with smoke_sensor as (
  select e.id entity_id
  from hc.entity e
  join hc.device d on d.id = e.device_id
  where d.platform = 'zigbee' and d.ext_id = '0x403802fffeb11030'
), metric_seed(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) as (
  values
    ('smoke', 'both', null::double precision, 1, 86400),
    ('tamper', 'both', null::double precision, 1, 86400),
    ('trouble', 'both', null::double precision, 1, 86400),
    ('test', 'both', null::double precision, 1, 86400),
    ('battery_defect', 'both', null::double precision, 1, 86400),
    ('battery_low', 'both', null::double precision, 1, 86400),
    ('battery', 'both', 1::double precision, 3600, 86400),
    ('linkquality', 'state', null::double precision, 3600, 86400)
)
insert into hc.entity_metric (
  entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled
)
select smoke_sensor.entity_id, metric_seed.metric_key, metric_seed.store_mode,
       metric_seed.deadband_num, metric_seed.min_interval_sec, metric_seed.max_interval_sec, true
from smoke_sensor cross join metric_seed
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'combustion_smoke_sensor', e.id, now()
from hc.entity e
where e.topic_base = 'zigbee/0x403802fffeb11030'
order by e.id
limit 1
on conflict (process_key) do update set
  entity_id = excluded.entity_id,
  updated_at = now();

commit;
