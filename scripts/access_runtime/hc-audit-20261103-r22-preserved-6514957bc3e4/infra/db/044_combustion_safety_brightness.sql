begin;

alter table hc.combustion_safety_config
  add column if not exists green_brightness integer not null default 50,
  add column if not exists orange_brightness integer not null default 200,
  add column if not exists red_brightness integer not null default 254;

alter table hc.combustion_safety_config
  drop constraint if exists combustion_safety_config_green_brightness_check,
  drop constraint if exists combustion_safety_config_orange_brightness_check,
  drop constraint if exists combustion_safety_config_red_brightness_check;

alter table hc.combustion_safety_config
  add constraint combustion_safety_config_green_brightness_check check (green_brightness between 1 and 254),
  add constraint combustion_safety_config_orange_brightness_check check (orange_brightness between 1 and 254),
  add constraint combustion_safety_config_red_brightness_check check (red_brightness between 1 and 254);

commit;
