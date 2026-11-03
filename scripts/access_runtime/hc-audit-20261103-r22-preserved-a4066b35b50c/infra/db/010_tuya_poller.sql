begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('power_w', 'num', 'W', 0, 10000, 'Tuya plug active power', true, true),
  ('voltage_v', 'num', 'V', 0, 300, 'Tuya plug mains voltage', true, true),
  ('current_a', 'num', 'A', 0, 100, 'Tuya plug current', true, true),
  ('energy_calc_kwh', 'num', 'kWh', 0, null, 'Tuya poller calculated energy', true, true),
  ('lag_sec', 'num', 's', 0, 86400, 'Tuya status source lag', true, true),
  ('recv_ts', 'num', 'unix_s', 0, null, 'Tuya poller receive timestamp', false, true),
  ('src_ts', 'num', 'unix_s', 0, null, 'Tuya device source timestamp', false, true),
  ('switch_state', 'bool', null, null, null, 'Switch on/off state', false, true),
  ('energy_kwh', 'num', 'kWh', 0, null, 'Energy counter', true, true)
on conflict (key) do update set
  value_type = excluded.value_type,
  unit = excluded.unit,
  min_num = excluded.min_num,
  max_num = excluded.max_num,
  description = excluded.description,
  enforce_validation = excluded.enforce_validation,
  is_active = true;

update hc.device
set ext_id = 'bfd72d3a347451925dbnnl',
    name = 'Mosógép',
    model = 'Smart plug',
    manufacturer = 'Tuya',
    is_active = true,
    updated_at = now()
where platform = 'tuya'
  and (ext_id is null or ext_id = '')
  and name = 'Mosógép'
  and not exists (
    select 1
    from hc.device d2
    where d2.platform = 'tuya'
      and d2.ext_id = 'bfd72d3a347451925dbnnl'
      and d2.id <> hc.device.id
  );

with tuya_devices(ext_id, name, ip) as (
  values
    ('bfa6191bb1ef666ed4lta7', 'Szárítógép', '192.168.1.185'),
    ('bf12e6fa75af31c5ec4koo', 'Fagyasztó', '192.168.1.113'),
    ('bfe74ef3bcf42b6e71cbxb', 'Nyestriasztó', '192.168.1.7'),
    ('bfd72d3a347451925dbnnl', 'Mosógép', '192.168.1.132'),
    ('bf6ac883a687a6a2a2ci8l', 'Mosogatógép', '192.168.1.166'),
    ('bf5323c55e90e5ba46axry', 'PC', '192.168.1.41')
),
device_upsert as (
  insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
  select 'tuya', ext_id, name, null, 'Smart plug', 'Tuya', true
  from tuya_devices
  on conflict (platform, ext_id) do update set
    name = excluded.name,
    model = excluded.model,
    manufacturer = excluded.manufacturer,
    is_active = true,
    updated_at = now()
  returning id, ext_id, name
)
insert into hc.entity (device_id, name, topic_base, is_active)
select id, name, 'homecontrol/tele/tuya/' || name, true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

update hc.entity e
set topic_base = null,
    is_active = false
from hc.device d
where e.device_id = d.id
  and d.platform = 'tuya'
  and d.ext_id = 'bfd72d3a347451925dbnnl'
  and e.name = 'main';

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('switch_state', 'both', null::double precision, 1, 300),
  ('power_w', 'both', 1::double precision, 5, 300),
  ('voltage_v', 'both', 0.5::double precision, 30, 600),
  ('current_a', 'both', 0.02::double precision, 5, 300),
  ('energy_kwh', 'both', 0.01::double precision, 60, 3600),
  ('energy_calc_kwh', 'state', 0.01::double precision, 60, 3600),
  ('lag_sec', 'state', null::double precision, 30, 300),
  ('recv_ts', 'state', null::double precision, 30, 300),
  ('src_ts', 'state', null::double precision, 30, 300)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'tuya'
  and d.ext_id in (
    'bfa6191bb1ef666ed4lta7',
    'bf12e6fa75af31c5ec4koo',
    'bfe74ef3bcf42b6e71cbxb',
    'bfd72d3a347451925dbnnl',
    'bf6ac883a687a6a2a2ci8l',
    'bf5323c55e90e5ba46axry'
  )
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
