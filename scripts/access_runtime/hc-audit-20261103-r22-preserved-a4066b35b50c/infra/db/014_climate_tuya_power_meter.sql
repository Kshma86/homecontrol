begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('power_w', 'num', 'W', 0, 10000, 'Active power', true, true),
  ('voltage_v', 'num', 'V', 0, 300, 'Mains voltage', true, true),
  ('current_a', 'num', 'A', 0, 100, 'Current', true, true),
  ('energy_kwh', 'num', 'kWh', 0, null, 'Energy counter', true, true),
  ('energy_calc_kwh', 'num', 'kWh', 0, null, 'Poller calculated energy', true, true),
  ('lag_sec', 'num', 's', 0, 86400, 'Source lag', true, true),
  ('recv_ts', 'num', 'unix_s', 0, null, 'Receive timestamp', false, true),
  ('src_ts', 'num', 'unix_s', 0, null, 'Source timestamp', false, true),
  ('tuya_raw_dps', 'json', null, null, null, 'Raw Tuya DPS snapshot', false, true)
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
  values ('tuya', 'bf7bda0d19d3934720scjs', 'Klíma fogyasztásmérő', 'Klíma', 'Energy meter', 'Tuya', true)
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
select id, 'Klíma fogyasztásmérő', 'homecontrol/tele/tuya/Klíma/Klíma fogyasztásmérő', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('power_w', 'both', 1::double precision, 5, 300),
  ('voltage_v', 'both', 0.5::double precision, 30, 600),
  ('current_a', 'both', 0.02::double precision, 5, 300),
  ('energy_kwh', 'both', 0.01::double precision, 60, 3600),
  ('energy_calc_kwh', 'state', 0.01::double precision, 60, 3600),
  ('lag_sec', 'state', null::double precision, 30, 300),
  ('recv_ts', 'state', null::double precision, 30, 300),
  ('src_ts', 'state', null::double precision, 30, 300),
  ('tuya_raw_dps', 'state', null::double precision, 5, 300)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'tuya'
  and d.ext_id = 'bf7bda0d19d3934720scjs'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
