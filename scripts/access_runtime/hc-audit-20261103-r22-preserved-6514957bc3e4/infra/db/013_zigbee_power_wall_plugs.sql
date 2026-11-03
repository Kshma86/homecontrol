begin;

with plug_seed(ext_id, entity_name, device_name, location, manufacturer) as (
  values
    ('0x0c4314fffe54b5df', 'Felső előszoba konnektor', 'Konnektor', 'Felső előszoba', '_TZ3000_5f43h46b'),
    ('0xa4c1380cb1bf299f', 'Zöld szoba konnektor', 'Konnektor', 'Zöld szoba', 'Zbeacon'),
    ('0xa4c13812631a96d4', 'Konyha elszívó', 'Konnektor', 'Konyha', 'Zbeacon'),
    ('0xa4c138266bdc9eed', 'Fali_conn1', 'Fali konn', 'Garázs', '_TZ3210_4ux0ondb'),
    ('0xa4c1383c15ca3e28', 'Nappali_asztal', 'Konnektor', 'Nappali', 'Zbeacon'),
    ('0xa4c13867f35faf83', 'Kisház', 'Konnektor', 'Kisház', 'Zbeacon'),
    ('0xa4c13877cfe5f05d', 'Pince ajtó felett', 'Konnektor', 'Pince', 'Zbeacon'),
    ('0xa4c1389dd07cff5f', 'Nyári konyha ajtó felett', 'Fali konn', 'Nyári konyha', '_TZ3210_4ux0ondb'),
    ('0xa4c138aed71a3462', 'Mosó szárító', 'Mosógép', 'Nyári konyha', 'Zbeacon'),
    ('0xa4c138ec52cfc4af', 'Fehér szoba szekrényen', 'Konnektor', 'Fehér szoba', 'Zbeacon'),
    ('0xa4c138f271c49a6c', 'Lila szoba', 'Konnektor', 'Lila szoba', 'Zbeacon'),
    ('0xa4c138f4233f0643', 'Mosogatógép', 'Konnektor', 'Konyha', 'Zbeacon')
)
insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
select 'zigbee', ext_id, device_name, location, 'TS011F', manufacturer, true
from plug_seed
on conflict (platform, ext_id) do update set
  name = excluded.name,
  location = excluded.location,
  model = excluded.model,
  manufacturer = excluded.manufacturer,
  is_active = true,
  updated_at = now();

with plug_seed(ext_id, entity_name) as (
  values
    ('0x0c4314fffe54b5df', 'Felső előszoba konnektor'),
    ('0xa4c1380cb1bf299f', 'Zöld szoba konnektor'),
    ('0xa4c13812631a96d4', 'Konyha elszívó'),
    ('0xa4c138266bdc9eed', 'Fali_conn1'),
    ('0xa4c1383c15ca3e28', 'Nappali_asztal'),
    ('0xa4c13867f35faf83', 'Kisház'),
    ('0xa4c13877cfe5f05d', 'Pince ajtó felett'),
    ('0xa4c1389dd07cff5f', 'Nyári konyha ajtó felett'),
    ('0xa4c138aed71a3462', 'Mosó szárító'),
    ('0xa4c138ec52cfc4af', 'Fehér szoba szekrényen'),
    ('0xa4c138f271c49a6c', 'Lila szoba'),
    ('0xa4c138f4233f0643', 'Mosogatógép')
),
device_rows as (
  select d.id as device_id, s.ext_id, s.entity_name
  from plug_seed s
  join hc.device d on d.platform = 'zigbee' and d.ext_id = s.ext_id
),
inserted as (
  insert into hc.entity (device_id, name, topic_base, is_active)
  select device_id, entity_name, 'zigbee/' || ext_id, true
  from device_rows dr
  where not exists (
    select 1
    from hc.entity existing
    where existing.device_id = dr.device_id
  )
  returning device_id
)
update hc.entity e
set name = dr.entity_name,
    topic_base = 'zigbee/' || dr.ext_id,
    is_active = true
from device_rows dr
where e.device_id = dr.device_id;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('switch_state', 'bool', null, null, null, 'Switch on/off state', false, true),
  ('power', 'num', 'W', null, null, 'Instant active power', false, true),
  ('current', 'num', 'A', null, null, 'Instant current', false, true),
  ('energy_kwh', 'num', 'kWh', null, null, 'Delivered energy', false, true),
  ('mains_voltage_v', 'num', 'V', null, null, 'Mains voltage', false, true),
  ('linkquality', 'num', null, null, null, 'Zigbee link quality', false, true)
on conflict (key) do update set
  value_type = excluded.value_type,
  unit = excluded.unit,
  min_num = excluded.min_num,
  max_num = excluded.max_num,
  description = excluded.description,
  enforce_validation = excluded.enforce_validation,
  is_active = true;

with plug_entities as (
  select e.id as entity_id
  from hc.entity e
  join hc.device d on d.id = e.device_id
  where d.platform = 'zigbee'
    and d.ext_id in (
      '0x0c4314fffe54b5df',
      '0xa4c1380cb1bf299f',
      '0xa4c13812631a96d4',
      '0xa4c138266bdc9eed',
      '0xa4c1383c15ca3e28',
      '0xa4c13867f35faf83',
      '0xa4c13877cfe5f05d',
      '0xa4c1389dd07cff5f',
      '0xa4c138aed71a3462',
      '0xa4c138ec52cfc4af',
      '0xa4c138f271c49a6c',
      '0xa4c138f4233f0643'
    )
),
metric_seed(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) as (
  values
    ('switch_state', 'both', null::double precision, 1, 300),
    ('power', 'both', 1::double precision, 5, 300),
    ('current', 'both', 0.02::double precision, 5, 300),
    ('energy_kwh', 'both', 0.01::double precision, 30, 3600),
    ('mains_voltage_v', 'both', 1::double precision, 30, 600),
    ('linkquality', 'state', 1::double precision, 60, 600)
)
insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select pe.entity_id, ms.metric_key, ms.store_mode, ms.deadband_num, ms.min_interval_sec, ms.max_interval_sec, true
from plug_entities pe
cross join metric_seed ms
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
