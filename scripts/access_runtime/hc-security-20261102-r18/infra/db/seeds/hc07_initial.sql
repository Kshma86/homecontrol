-- HC-07: optional, journalled first-install defaults. Never run on application startup.
-- Existing inventory/configuration is never updated; this seed is not a repair command.



insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('water_leak', 'bool', null, null, null, 'Rain sensor wet/dry state', false, true),
  ('carbon_monoxide', 'bool', null, null, null, 'Carbon monoxide alarm state', false, true),
  ('carbon_monoxide_value', 'num', 'ppm', 0, 10000, 'Carbon monoxide concentration', true, true),
  ('fault', 'bool', null, null, null, 'Sensor fault state', false, true),
  ('lifecycle', 'bool', null, null, null, 'Sensor lifecycle state', false, true),
  ('battery_state', 'text', null, null, null, 'Battery condition reported by the device', false, true),
  ('battery_low', 'bool', null, null, null, 'Battery low flag', false, true),
  ('battery', 'num', '%', 0, 100, 'Battery percent', true, true),
  ('linkquality', 'num', null, 0, 255, 'Zigbee link quality', true, true)
on conflict (key) do nothing;


insert into hc.device(platform,ext_id,name,location,model,manufacturer,is_active)
values('zigbee','0xa4c1386ab8457e91','CO detector','Otthon','E12','Nous',true)
on conflict(platform,ext_id) do nothing;
insert into hc.entity(device_id,name,topic_base,is_active)
select d.id,'CO detector','zigbee/0xa4c1386ab8457e91',true from hc.device d
where d.platform='zigbee' and d.ext_id='0xa4c1386ab8457e91'
  and not exists(select 1 from hc.entity e where e.device_id=d.id)
on conflict(device_id,name) do nothing;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('carbon_monoxide', 'both', null::double precision, 1, 86400),
  ('carbon_monoxide_value', 'both', 1::double precision, 1, 3600),
  ('fault', 'both', null::double precision, 1, 86400),
  ('lifecycle', 'both', null::double precision, 1, 86400),
  ('battery_state', 'both', null::double precision, 1, 86400)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'zigbee' and d.ext_id = '0xa4c1386ab8457e91'
on conflict (entity_id, metric_key) do nothing;

insert into hc.device(platform,ext_id,name,location,model,manufacturer,is_active)
values('zigbee','0xa4c138479ed598c1','Rain sensor','Udvar','TS0207','Tuya',true)
on conflict(platform,ext_id) do nothing;
insert into hc.entity(device_id,name,topic_base,is_active)
select d.id,'Rain sensor','zigbee/0xa4c138479ed598c1',true from hc.device d
where d.platform='zigbee' and d.ext_id='0xa4c138479ed598c1'
  and not exists(select 1 from hc.entity e where e.device_id=d.id)
on conflict(device_id,name) do nothing;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('water_leak', 'both', null::double precision, 1, 86400),
  ('battery_low', 'both', null::double precision, 1, 86400),
  ('battery', 'both', 1::double precision, 3600, 86400),
  ('linkquality', 'both', null::double precision, 3600, 86400)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'zigbee' and d.ext_id = '0xa4c138479ed598c1'
on conflict (entity_id, metric_key) do nothing;

insert into hc.irrigation_pilot_config(id) values(1) on conflict(id) do nothing;
insert into hc.irrigation_solar_pump_config(id) values(1) on conflict(id) do nothing;
insert into hc.scheduler_config(id) values(1) on conflict(id) do nothing;
insert into hc.climate_schedule_rule (
  label,
  day_of_week,
  start_time,
  is_enabled,
  power,
  mode,
  target_temperature,
  fan_speed,
  light,
  rule_engine
)
select
  seed.label,
  seed.day_of_week,
  seed.start_time,
  false,
  'on',
  'heat',
  23,
  'auto',
  'off',
  '{"stage":"bootstrap","rule_engine":"manual_schedule"}'::jsonb
from (values
  ('Monday', 0::smallint, '06:30'::time),
  ('Tuesday', 1::smallint, '06:30'::time),
  ('Wednesday', 2::smallint, '06:30'::time),
  ('Thursday', 3::smallint, '06:30'::time),
  ('Friday', 4::smallint, '06:30'::time),
  ('Saturday', 5::smallint, '06:30'::time),
  ('Sunday', 6::smallint, '06:30'::time)
) as seed(label, day_of_week, start_time)
where not exists (
  select 1
  from hc.climate_schedule_rule existing
  where existing.day_of_week = seed.day_of_week
);

insert into hc.domain_season_profile(domain,profile,settings) values
 ('irrigation','summer','{"manual_watering":true,"scheduled_watering":true,"solar_pump_automation":true,"maintenance_controls":true,"measurements_logging":true}'::jsonb),
 ('irrigation','winter','{"manual_watering":false,"scheduled_watering":false,"solar_pump_automation":false,"maintenance_controls":false,"measurements_logging":true}'::jsonb),
 ('climate','summer','{}'::jsonb),('climate','winter','{}'::jsonb)
on conflict(domain,profile) do nothing;
insert into hc.domain_season_active(domain,profile) values('irrigation','summer'),('climate','summer') on conflict(domain) do nothing;
