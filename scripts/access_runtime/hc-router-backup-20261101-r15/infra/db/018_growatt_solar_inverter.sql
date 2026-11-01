alter type hc.platform_t add value if not exists 'growatt';

begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('growatt_pv_power_in_w', 'num', 'W', 0, 100000, 'Growatt PV input power', true, true),
  ('growatt_pv_power_out_w', 'num', 'W', 0, 100000, 'Growatt AC output power', true, true),
  ('growatt_pv1_power_w', 'num', 'W', 0, 50000, 'Growatt PV string 1 power', true, true),
  ('growatt_pv2_power_w', 'num', 'W', 0, 50000, 'Growatt PV string 2 power', true, true),
  ('growatt_pv3_power_w', 'num', 'W', 0, 50000, 'Growatt PV string 3 power', true, true),
  ('growatt_grid_power_l1_w', 'num', 'W', -50000, 50000, 'Growatt grid phase 1 power', true, true),
  ('growatt_grid_power_l2_w', 'num', 'W', -50000, 50000, 'Growatt grid phase 2 power', true, true),
  ('growatt_grid_power_l3_w', 'num', 'W', -50000, 50000, 'Growatt grid phase 3 power', true, true),
  ('growatt_pv1_voltage_v', 'num', 'V', 0, 1000, 'Growatt PV string 1 voltage', true, true),
  ('growatt_pv2_voltage_v', 'num', 'V', 0, 1000, 'Growatt PV string 2 voltage', true, true),
  ('growatt_pv3_voltage_v', 'num', 'V', 0, 1000, 'Growatt PV string 3 voltage', true, true),
  ('growatt_grid_voltage_l1_v', 'num', 'V', 0, 300, 'Growatt grid phase 1 voltage', true, true),
  ('growatt_grid_voltage_l2_v', 'num', 'V', 0, 300, 'Growatt grid phase 2 voltage', true, true),
  ('growatt_grid_voltage_l3_v', 'num', 'V', 0, 300, 'Growatt grid phase 3 voltage', true, true),
  ('growatt_pv1_current_a', 'num', 'A', 0, 200, 'Growatt PV string 1 current', true, true),
  ('growatt_pv2_current_a', 'num', 'A', 0, 200, 'Growatt PV string 2 current', true, true),
  ('growatt_pv3_current_a', 'num', 'A', 0, 200, 'Growatt PV string 3 current', true, true),
  ('growatt_grid_current_l1_a', 'num', 'A', 0, 200, 'Growatt grid phase 1 current', true, true),
  ('growatt_grid_current_l2_a', 'num', 'A', 0, 200, 'Growatt grid phase 2 current', true, true),
  ('growatt_grid_current_l3_a', 'num', 'A', 0, 200, 'Growatt grid phase 3 current', true, true),
  ('growatt_grid_frequency_hz', 'num', 'Hz', 0, 100, 'Growatt grid frequency', true, true),
  ('growatt_energy_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt generated energy today', true, true),
  ('growatt_energy_total_kwh', 'num', 'kWh', 0, null, 'Growatt generated energy total', true, true),
  ('growatt_pv1_energy_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt PV string 1 energy today', true, true),
  ('growatt_pv1_energy_total_kwh', 'num', 'kWh', 0, null, 'Growatt PV string 1 energy total', true, true),
  ('growatt_pv2_energy_today_kwh', 'num', 'kWh', 0, 10000, 'Growatt PV string 2 energy today', true, true),
  ('growatt_pv2_energy_total_kwh', 'num', 'kWh', 0, null, 'Growatt PV string 2 energy total', true, true),
  ('growatt_pv_energy_total_kwh', 'num', 'kWh', 0, null, 'Growatt PV strings energy total', true, true),
  ('growatt_inverter_temperature_c', 'num', 'C', -40, 150, 'Growatt inverter temperature', true, true),
  ('growatt_ipm_temperature_c', 'num', 'C', -40, 150, 'Growatt IPM temperature', true, true),
  ('growatt_total_work_time_s', 'num', 's', 0, null, 'Growatt inverter total work time', true, true),
  ('growatt_status_code', 'num', null, 0, 20, 'Growatt inverter status code', true, true),
  ('growatt_device', 'text', null, null, null, 'Growatt inverter serial from MQTT payload', false, true),
  ('growatt_sample_time', 'text', null, null, null, 'Growatt sample timestamp from MQTT payload', false, true),
  ('growatt_buffered', 'text', null, null, null, 'Growatt buffered sample marker', false, true)
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
  values ('growatt', 'growatt-inverter', 'Growatt solar inverter', 'Solar', 'Solar inverter', 'Growatt', true)
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
select id, 'Growatt solar inverter', 'homecontrol/tele/growatt/inverter', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('growatt_pv_power_in_w', 'both', 10::double precision, 10, 300),
  ('growatt_pv_power_out_w', 'both', 10::double precision, 10, 300),
  ('growatt_pv1_power_w', 'both', 10::double precision, 10, 300),
  ('growatt_pv2_power_w', 'both', 10::double precision, 10, 300),
  ('growatt_pv3_power_w', 'both', 10::double precision, 10, 300),
  ('growatt_grid_power_l1_w', 'both', 10::double precision, 10, 300),
  ('growatt_grid_power_l2_w', 'both', 10::double precision, 10, 300),
  ('growatt_grid_power_l3_w', 'both', 10::double precision, 10, 300),
  ('growatt_pv1_voltage_v', 'both', 0.5::double precision, 30, 600),
  ('growatt_pv2_voltage_v', 'both', 0.5::double precision, 30, 600),
  ('growatt_pv3_voltage_v', 'both', 0.5::double precision, 30, 600),
  ('growatt_grid_voltage_l1_v', 'both', 0.5::double precision, 30, 600),
  ('growatt_grid_voltage_l2_v', 'both', 0.5::double precision, 30, 600),
  ('growatt_grid_voltage_l3_v', 'both', 0.5::double precision, 30, 600),
  ('growatt_pv1_current_a', 'both', 0.1::double precision, 30, 600),
  ('growatt_pv2_current_a', 'both', 0.1::double precision, 30, 600),
  ('growatt_pv3_current_a', 'both', 0.1::double precision, 30, 600),
  ('growatt_grid_current_l1_a', 'both', 0.1::double precision, 30, 600),
  ('growatt_grid_current_l2_a', 'both', 0.1::double precision, 30, 600),
  ('growatt_grid_current_l3_a', 'both', 0.1::double precision, 30, 600),
  ('growatt_grid_frequency_hz', 'both', 0.02::double precision, 30, 600),
  ('growatt_energy_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('growatt_energy_total_kwh', 'both', 0.1::double precision, 300, 3600),
  ('growatt_pv1_energy_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('growatt_pv1_energy_total_kwh', 'both', 0.1::double precision, 300, 3600),
  ('growatt_pv2_energy_today_kwh', 'both', 0.1::double precision, 60, 900),
  ('growatt_pv2_energy_total_kwh', 'both', 0.1::double precision, 300, 3600),
  ('growatt_pv_energy_total_kwh', 'both', 0.1::double precision, 300, 3600),
  ('growatt_inverter_temperature_c', 'both', 0.5::double precision, 30, 600),
  ('growatt_ipm_temperature_c', 'both', 0.5::double precision, 30, 600),
  ('growatt_total_work_time_s', 'state', 60::double precision, 300, 3600),
  ('growatt_status_code', 'both', null::double precision, 1, 300),
  ('growatt_device', 'state', null::double precision, 300, 86400),
  ('growatt_sample_time', 'state', null::double precision, 60, 900),
  ('growatt_buffered', 'state', null::double precision, 60, 900)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'growatt'
  and d.ext_id = 'growatt-inverter'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
