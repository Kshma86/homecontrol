begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('dry', 'bool', null, null, null, 'Soil moisture dry flag', false, true),
  ('soil_warning', 'num', '%', 0, 100, 'Soil moisture warning threshold reported by sensor', true, true),
  ('soil_sampling', 'num', 's', 1, 86400, 'Soil moisture sampling interval reported by sensor', true, true),
  ('soil_calibration', 'num', null, -100, 100, 'Soil moisture calibration reported by sensor', true, true),
  ('humidity_calibration', 'num', null, -100, 100, 'Humidity calibration reported by sensor', true, true),
  ('temperature_calibration', 'num', null, -100, 100, 'Temperature calibration reported by sensor', true, true),
  ('temperature_sampling', 'num', 's', 1, 86400, 'Temperature sampling interval reported by sensor', true, true),
  ('temperature_unit', 'text', null, null, null, 'Temperature unit reported by sensor', false, true)
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
  values ('zigbee', '0xa4c1387594b09c83', 'Moisture_03', 'Flower garden', 'ZG-303Z', 'HOBEIAN', true)
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
select id, 'Moisture_03', 'zigbee/0xa4c1387594b09c83', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('soil_moisture', 'both', 1::double precision, 30, 300),
  ('dry', 'both', null::double precision, 1, 300),
  ('temperature', 'both', 0.1::double precision, 30, 600),
  ('humidity', 'both', 1::double precision, 30, 600),
  ('battery', 'both', 1::double precision, 300, 21600),
  ('linkquality', 'both', null::double precision, 3600, 3600),
  ('soil_warning', 'both', null::double precision, 3600, 21600),
  ('soil_sampling', 'both', null::double precision, 3600, 21600),
  ('soil_calibration', 'both', null::double precision, 3600, 21600),
  ('humidity_calibration', 'both', null::double precision, 3600, 21600),
  ('temperature_calibration', 'both', null::double precision, 3600, 21600),
  ('temperature_sampling', 'both', null::double precision, 3600, 21600),
  ('temperature_unit', 'both', null::double precision, 3600, 21600)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'zigbee' and d.ext_id = '0xa4c1387594b09c83'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
