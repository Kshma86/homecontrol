begin;
alter table hc.combustion_safety_config
  add column if not exists green_color text not null default '#00ff00',
  add column if not exists orange_color text not null default '#ff8c00',
  add column if not exists red_color text not null default '#ff0000';
alter table hc.combustion_safety_config
  drop constraint if exists combustion_safety_config_green_color_check,
  drop constraint if exists combustion_safety_config_orange_color_check,
  drop constraint if exists combustion_safety_config_red_color_check;
alter table hc.combustion_safety_config
  add constraint combustion_safety_config_green_color_check check (green_color ~ '^#[0-9A-Fa-f]{6}$'),
  add constraint combustion_safety_config_orange_color_check check (orange_color ~ '^#[0-9A-Fa-f]{6}$'),
  add constraint combustion_safety_config_red_color_check check (red_color ~ '^#[0-9A-Fa-f]{6}$');
commit;
