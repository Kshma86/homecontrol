begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('system_power_w', 'num', 'W', -100000, 100000, 'Growatt system power from Home Assistant', true, true),
  ('output_power_w', 'num', 'W', -100000, 100000, 'Growatt inverter output power from Home Assistant', true, true),
  ('energy_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt inverter energy today from Home Assistant', true, true),
  ('lifetime_energy_kwh', 'num', 'kWh', 0, null, 'Growatt inverter lifetime energy from Home Assistant', true, true),
  ('solar_energy_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt solar energy today from Home Assistant', true, true),
  ('lifetime_solar_energy_kwh', 'num', 'kWh', 0, null, 'Growatt lifetime solar energy from Home Assistant', true, true),
  ('battery_soc_percent', 'num', '%', 0, 100, 'Growatt battery state of charge from Home Assistant', true, true),
  ('local_load_power_w', 'num', 'W', -100000, 100000, 'Growatt local load power from Home Assistant', true, true),
  ('import_power_w', 'num', 'W', -100000, 100000, 'Growatt grid import power from Home Assistant', true, true),
  ('export_power_w', 'num', 'W', -100000, 100000, 'Growatt grid export power from Home Assistant', true, true),
  ('load_consumption_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt load consumption today from Home Assistant', true, true),
  ('lifetime_load_consumption_kwh', 'num', 'kWh', 0, null, 'Growatt lifetime load consumption from Home Assistant', true, true),
  ('export_to_grid_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt export to grid today from Home Assistant', true, true),
  ('lifetime_export_to_grid_kwh', 'num', 'kWh', 0, null, 'Growatt lifetime export to grid from Home Assistant', true, true),
  ('import_from_grid_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt import from grid today from Home Assistant', true, true),
  ('lifetime_import_from_grid_kwh', 'num', 'kWh', 0, null, 'Growatt lifetime import from grid from Home Assistant', true, true),
  ('self_consumption_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt self consumption today from Home Assistant', true, true),
  ('lifetime_self_consumption_kwh', 'num', 'kWh', 0, null, 'Growatt lifetime self consumption from Home Assistant', true, true),
  ('input_1_wattage_w', 'num', 'W', 0, 50000, 'Growatt PV input 1 wattage from Home Assistant', true, true),
  ('input_2_wattage_w', 'num', 'W', 0, 50000, 'Growatt PV input 2 wattage from Home Assistant', true, true),
  ('input_1_voltage_v', 'num', 'V', 0, 1000, 'Growatt PV input 1 voltage from Home Assistant', true, true),
  ('input_2_voltage_v', 'num', 'V', 0, 1000, 'Growatt PV input 2 voltage from Home Assistant', true, true),
  ('input_1_current_a', 'num', 'A', 0, 200, 'Growatt PV input 1 current from Home Assistant', true, true),
  ('input_2_current_a', 'num', 'A', 0, 200, 'Growatt PV input 2 current from Home Assistant', true, true),
  ('ac_frequency_hz', 'num', 'Hz', 0, 100, 'Growatt AC frequency from Home Assistant', true, true),
  ('temperature_1_c', 'num', 'C', -40, 150, 'Growatt temperature 1 from Home Assistant', true, true),
  ('plant_output_power_w', 'num', 'W', -100000, 100000, 'Growatt plant output power from Home Assistant', true, true),
  ('plant_energy_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt plant energy today from Home Assistant', true, true),
  ('plant_lifetime_energy_kwh', 'num', 'kWh', 0, null, 'Growatt plant lifetime energy from Home Assistant', true, true),
  ('entity_count', 'num', null, 0, 1000, 'Number of Growatt Home Assistant entities fetched', true, true),
  ('sample_time', 'text', null, null, null, 'Growatt Home Assistant poll sample time', false, true),
  ('source', 'text', null, null, null, 'Growatt source system', false, true),
  ('meta', 'json', null, null, null, 'Growatt Home Assistant poll metadata', false, true)
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
  values ('growatt', 'ha-growatt-cloud', 'Growatt cloud via Home Assistant', 'Solar', 'Growatt HA cloud', 'Growatt', true)
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
select id, 'Growatt cloud via Home Assistant', 'homecontrol/tele/growatt/cloud', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('system_power_w', 'both', 10::double precision, 30, 300),
  ('output_power_w', 'both', 10::double precision, 30, 300),
  ('energy_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('lifetime_energy_kwh', 'both', 0.1::double precision, 300, 3600),
  ('solar_energy_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('lifetime_solar_energy_kwh', 'both', 0.1::double precision, 300, 3600),
  ('battery_soc_percent', 'both', 1::double precision, 60, 900),
  ('local_load_power_w', 'both', 10::double precision, 30, 300),
  ('import_power_w', 'both', 10::double precision, 30, 300),
  ('export_power_w', 'both', 10::double precision, 30, 300),
  ('load_consumption_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('lifetime_load_consumption_kwh', 'both', 0.1::double precision, 300, 3600),
  ('export_to_grid_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('lifetime_export_to_grid_kwh', 'both', 0.1::double precision, 300, 3600),
  ('import_from_grid_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('lifetime_import_from_grid_kwh', 'both', 0.1::double precision, 300, 3600),
  ('self_consumption_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('lifetime_self_consumption_kwh', 'both', 0.1::double precision, 300, 3600),
  ('input_1_wattage_w', 'both', 10::double precision, 30, 300),
  ('input_2_wattage_w', 'both', 10::double precision, 30, 300),
  ('input_1_voltage_v', 'both', 0.5::double precision, 60, 600),
  ('input_2_voltage_v', 'both', 0.5::double precision, 60, 600),
  ('input_1_current_a', 'both', 0.1::double precision, 60, 600),
  ('input_2_current_a', 'both', 0.1::double precision, 60, 600),
  ('ac_frequency_hz', 'both', 0.02::double precision, 60, 600),
  ('temperature_1_c', 'both', 0.5::double precision, 60, 600),
  ('plant_output_power_w', 'both', 10::double precision, 30, 300),
  ('plant_energy_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('plant_lifetime_energy_kwh', 'both', 0.1::double precision, 300, 3600),
  ('entity_count', 'state', null::double precision, 60, 900),
  ('sample_time', 'state', null::double precision, 60, 900),
  ('source', 'state', null::double precision, 300, 86400),
  ('meta', 'state', null::double precision, 60, 900)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'growatt'
  and d.ext_id = 'ha-growatt-cloud'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
