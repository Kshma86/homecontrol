begin;

alter table hc.irrigation_pilot_config
  add column if not exists soil_moisture_enabled boolean not null default true,
  add column if not exists soil_sensor_topic_base text not null default 'zigbee/0xa4c13844a0908898',
  add column if not exists soil_wet_skip_threshold_percent numeric not null default 85,
  add column if not exists soil_dry_threshold_percent numeric not null default 45,
  add column if not exists soil_dry_correction_percent integer not null default 15,
  add column if not exists soil_sample_max_age_hours integer not null default 12;

update hc.irrigation_pilot_config
set soil_sensor_topic_base = 'zigbee/0xa4c13844a0908898'
where id = 1
  and (soil_sensor_topic_base is null or soil_sensor_topic_base = '');

commit;
