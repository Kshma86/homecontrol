begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('x10_robot_state', 'num', null, 0, 999, 'Xiaomi X10 numeric robot state', true, true),
  ('x10_robot_state_text', 'text', null, null, null, 'Xiaomi X10 robot state text', false, true),
  ('x10_charge_status', 'num', null, 0, 999, 'Xiaomi X10 charge or dock status', true, true),
  ('x10_task_state', 'num', null, 0, 999, 'Xiaomi X10 internal task state', true, true),
  ('x10_clean_mode', 'num', null, 0, 999, 'Xiaomi X10 clean mode', true, true),
  ('x10_mop_attached', 'bool', null, null, null, 'Xiaomi X10 mop attached', false, true),
  ('x10_suction', 'num', null, 0, 999, 'Xiaomi X10 suction level', true, true),
  ('x10_water_level', 'num', null, 0, 999, 'Xiaomi X10 water level', true, true),
  ('x10_bridge_online', 'bool', null, null, null, 'Xiaomi X10 bridge online state', false, true),
  ('x10_bridge_status', 'text', null, null, null, 'Xiaomi X10 bridge status text', false, true),
  ('x10_bridge_last_seen', 'num', 'unix_s', 0, null, 'Xiaomi X10 bridge last seen epoch', false, true),
  ('x10_state', 'json', null, null, null, 'Xiaomi X10 full state payload', false, true),
  ('x10_command_result', 'json', null, null, null, 'Xiaomi X10 latest command result', false, true),
  ('x10_error', 'json', null, null, null, 'Xiaomi X10 latest error', false, true),
  ('x10_map_count', 'num', null, 0, 100, 'Xiaomi X10 saved map count', true, true),
  ('x10_map_current_id', 'num', null, 0, 1000000, 'Xiaomi X10 current map id', true, true),
  ('x10_map_current_id_from_index', 'num', null, 0, 1000000, 'Xiaomi X10 current map id from index', true, true),
  ('x10_map_current_name', 'text', null, null, null, 'Xiaomi X10 current map name', false, true),
  ('x10_map_current_png', 'text', null, null, null, 'Xiaomi X10 current map image path', false, true),
  ('x10_map_md5', 'text', null, null, null, 'Xiaomi X10 map md5', false, true),
  ('x10_map_object_name', 'text', null, null, null, 'Xiaomi X10 map cloud object name', false, true),
  ('x10_map_current', 'json', null, null, null, 'Xiaomi X10 current map metadata', false, true),
  ('x10_map_room_names', 'json', null, null, null, 'Xiaomi X10 room names', false, true),
  ('x10_map_rooms', 'json', null, null, null, 'Xiaomi X10 rooms', false, true),
  ('x10_map_rooms_raw', 'json', null, null, null, 'Xiaomi X10 raw rooms', false, true),
  ('x10_map_rooms_normalized', 'json', null, null, null, 'Xiaomi X10 normalized rooms', false, true),
  ('x10_map_index', 'json', null, null, null, 'Xiaomi X10 map index', false, true),
  ('x10_map_object', 'json', null, null, null, 'Xiaomi X10 map object', false, true),
  ('x10_robot_header_raw', 'json', null, null, null, 'Xiaomi X10 raw robot map header', false, true),
  ('x10_robot_position', 'json', null, null, null, 'Xiaomi X10 robot world position', false, true),
  ('x10_robot_position_px', 'json', null, null, null, 'Xiaomi X10 robot pixel position', false, true),
  ('x10_dock_position', 'json', null, null, null, 'Xiaomi X10 dock world position', false, true),
  ('x10_dock_position_px', 'json', null, null, null, 'Xiaomi X10 dock pixel position', false, true),
  ('x10_room_clean_request', 'json', null, null, null, 'Xiaomi X10 room clean request', false, true),
  ('x10_room_clean_status', 'json', null, null, null, 'Xiaomi X10 room clean status', false, true),
  ('x10_room_clean_task', 'json', null, null, null, 'Xiaomi X10 room clean scheduler task', false, true),
  ('x10_scheduler_last_read', 'num', 'unix_s', 0, null, 'Xiaomi X10 scheduler last read epoch', false, true),
  ('x10_scheduler_entries', 'json', null, null, null, 'Xiaomi X10 parsed scheduler entries', false, true),
  ('x10_scheduler_raw', 'text', null, null, null, 'Xiaomi X10 raw scheduler', false, true),
  ('x10_scheduler_write_candidate', 'text', null, null, null, 'Xiaomi X10 scheduler write candidate', false, true),
  ('x10_scheduler_write_result', 'text', null, null, null, 'Xiaomi X10 scheduler write result', false, true)
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
  values ('wifi', 'xiaomi-x10', 'Xiaomi X10', 'Ház', 'X10', 'Xiaomi', true)
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
select id, 'Xiaomi X10', 'homecontrol/xiaomi_x10', true
from device_upsert
on conflict (device_id, name) do update set
  topic_base = excluded.topic_base,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, v.metric_key, v.store_mode, v.deadband_num, v.min_interval_sec, v.max_interval_sec, true
from hc.entity e
join hc.device d on d.id = e.device_id
join (values
  ('battery', 'both', 1::double precision, 300, 3600),
  ('x10_robot_state', 'both', null::double precision, 1, 300),
  ('x10_robot_state_text', 'both', null::double precision, 1, 300),
  ('x10_charge_status', 'both', null::double precision, 1, 300),
  ('x10_task_state', 'both', null::double precision, 1, 300),
  ('x10_clean_mode', 'both', null::double precision, 30, 3600),
  ('x10_mop_attached', 'both', null::double precision, 30, 3600),
  ('x10_suction', 'both', null::double precision, 30, 3600),
  ('x10_water_level', 'both', null::double precision, 30, 3600),
  ('x10_bridge_online', 'both', null::double precision, 1, 300),
  ('x10_bridge_status', 'both', null::double precision, 1, 300),
  ('x10_bridge_last_seen', 'state', null::double precision, 1, 300),
  ('x10_state', 'state', null::double precision, 1, 300),
  ('x10_command_result', 'both', null::double precision, 1, 86400),
  ('x10_error', 'both', null::double precision, 1, 86400),
  ('x10_map_count', 'state', null::double precision, 60, 3600),
  ('x10_map_current_id', 'both', null::double precision, 60, 3600),
  ('x10_map_current_id_from_index', 'state', null::double precision, 60, 3600),
  ('x10_map_current_name', 'both', null::double precision, 60, 3600),
  ('x10_map_current_png', 'state', null::double precision, 60, 3600),
  ('x10_map_md5', 'both', null::double precision, 60, 3600),
  ('x10_map_object_name', 'state', null::double precision, 60, 3600),
  ('x10_map_current', 'state', null::double precision, 60, 3600),
  ('x10_map_room_names', 'state', null::double precision, 60, 3600),
  ('x10_map_rooms', 'state', null::double precision, 60, 3600),
  ('x10_map_rooms_raw', 'state', null::double precision, 60, 3600),
  ('x10_map_rooms_normalized', 'state', null::double precision, 60, 3600),
  ('x10_map_index', 'state', null::double precision, 60, 3600),
  ('x10_map_object', 'state', null::double precision, 60, 3600),
  ('x10_robot_header_raw', 'state', null::double precision, 10, 300),
  ('x10_robot_position', 'both', null::double precision, 10, 300),
  ('x10_robot_position_px', 'both', null::double precision, 10, 300),
  ('x10_dock_position', 'state', null::double precision, 60, 3600),
  ('x10_dock_position_px', 'state', null::double precision, 60, 3600),
  ('x10_room_clean_request', 'both', null::double precision, 1, 86400),
  ('x10_room_clean_status', 'both', null::double precision, 1, 300),
  ('x10_room_clean_task', 'state', null::double precision, 1, 300),
  ('x10_scheduler_last_read', 'state', null::double precision, 1, 300),
  ('x10_scheduler_entries', 'both', null::double precision, 1, 300),
  ('x10_scheduler_raw', 'state', null::double precision, 1, 300),
  ('x10_scheduler_write_candidate', 'state', null::double precision, 1, 300),
  ('x10_scheduler_write_result', 'state', null::double precision, 1, 300)
) as v(metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec) on true
where d.platform = 'wifi' and d.ext_id = 'xiaomi-x10'
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

create table if not exists hc.x10_schedule (
  entity_id bigint not null references hc.entity(id) on delete cascade,
  task_id integer not null,
  is_enabled boolean not null default false,
  start_time text not null,
  days text not null,
  clean_mode integer,
  map_id integer,
  suction integer,
  water_level integer,
  segments jsonb not null default '[]'::jsonb,
  raw text,
  is_weekly boolean not null default false,
  is_hc_owned boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (entity_id, task_id)
);

alter table hc.x10_schedule
  add column if not exists is_hc_owned boolean not null default false;

create index if not exists x10_schedule_entity_weekly_idx
  on hc.x10_schedule (entity_id, is_weekly, task_id);

create index if not exists x10_schedule_entity_owned_idx
  on hc.x10_schedule (entity_id, is_hc_owned, task_id);

create table if not exists hc.x10_schedule_day (
  entity_id bigint not null references hc.entity(id) on delete cascade,
  task_id integer not null,
  day_index integer not null check (day_index between 0 and 6),
  day_name text not null,
  is_enabled boolean not null default false,
  start_time text not null,
  clean_mode integer,
  map_id integer,
  suction integer,
  water_level integer,
  segments jsonb not null default '[]'::jsonb,
  raw text,
  is_hc_owned boolean not null default true,
  updated_at timestamptz not null default now(),
  primary key (entity_id, task_id, day_index)
);

alter table hc.x10_schedule_day
  add column if not exists is_hc_owned boolean not null default true;

create index if not exists x10_schedule_day_entity_day_idx
  on hc.x10_schedule_day (entity_id, day_index, start_time);

create index if not exists x10_schedule_day_entity_owned_idx
  on hc.x10_schedule_day (entity_id, is_hc_owned, day_index);

create table if not exists hc.x10_map (
  entity_id bigint not null references hc.entity(id) on delete cascade,
  map_id integer not null,
  name text not null,
  png text,
  md5 text,
  is_current boolean not null default false,
  has_room_data boolean not null default false,
  source text not null default 'seed',
  updated_at timestamptz not null default now(),
  primary key (entity_id, map_id)
);

create index if not exists x10_map_entity_name_idx
  on hc.x10_map (entity_id, name);

create table if not exists hc.x10_room (
  entity_id bigint not null references hc.entity(id) on delete cascade,
  map_id integer not null,
  segment_id integer not null,
  name text not null,
  room_id text,
  room_type integer,
  neighbors jsonb not null default '[]'::jsonb,
  is_active boolean not null default true,
  source text not null default 'seed',
  updated_at timestamptz not null default now(),
  primary key (entity_id, map_id, segment_id),
  foreign key (entity_id, map_id) references hc.x10_map(entity_id, map_id) on delete cascade
);

create index if not exists x10_room_entity_map_name_idx
  on hc.x10_room (entity_id, map_id, name);

with x10_entity as (
  select e.id as entity_id
  from hc.entity e
  join hc.device d on d.id = e.device_id
  where d.platform = 'wifi' and d.ext_id = 'xiaomi-x10'
)
insert into hc.x10_map (entity_id, map_id, name, has_room_data, source)
select entity_id, v.map_id, v.name, v.has_room_data, 'seed'
from x10_entity
cross join (values
  (3, 'Földszint', true),
  (197, '1. Szint', true),
  (44, '2. Szint', true)
) as v(map_id, name, has_room_data)
on conflict (entity_id, map_id) do update set
  name = excluded.name,
  has_room_data = hc.x10_map.has_room_data or excluded.has_room_data,
  updated_at = now();

with x10_entity as (
  select e.id as entity_id
  from hc.entity e
  join hc.device d on d.id = e.device_id
  where d.platform = 'wifi' and d.ext_id = 'xiaomi-x10'
)
insert into hc.x10_room (entity_id, map_id, segment_id, name, room_id, room_type, neighbors, source)
select entity_id, 3, v.segment_id, v.name, v.room_id, v.room_type, v.neighbors::jsonb, 'seed'
from x10_entity
cross join (values
  (1, 'Nappali', '48001097074', 0, '[2,5]'),
  (2, 'Előszoba', '48001097075', 0, '[1,3,4,7]'),
  (3, 'Fürdőszoba', '48001097076', 0, '[2,4]'),
  (4, 'Konyha', '48001097077', 0, '[2,3]'),
  (5, 'room_5', null, null, '[1]'),
  (7, 'WC', '48001097078', 0, '[2]')
) as v(segment_id, name, room_id, room_type, neighbors)
on conflict (entity_id, map_id, segment_id) do update set
  name = excluded.name,
  room_id = excluded.room_id,
  room_type = excluded.room_type,
  neighbors = excluded.neighbors,
  is_active = true,
  updated_at = now();

with x10_entity as (
  select e.id as entity_id
  from hc.entity e
  join hc.device d on d.id = e.device_id
  where d.platform = 'wifi' and d.ext_id = 'xiaomi-x10'
)
insert into hc.x10_room (entity_id, map_id, segment_id, name, room_id, room_type, neighbors, source)
select entity_id, v.map_id, v.segment_id, v.name, v.room_id, v.room_type, v.neighbors::jsonb, 'seed'
from x10_entity
cross join (values
  (197, 1, 'Zsófi szoba', '48001098232', 0, '[2]'),
  (197, 2, 'Lépcső forduló', '48001098235', 0, '[1,3]'),
  (197, 3, 'Anya-apa szoba', '48001098233', 0, '[2]'),
  (44, 1, 'Nyárikonyha', null, null, '[3]'),
  (44, 2, 'Fürdőszoba', '48001097076', 0, '[5]'),
  (44, 3, 'Fehér szoba', null, null, '[1,5]'),
  (44, 4, 'Zöld szoba', '48001100024', 0, '[5]'),
  (44, 5, 'Folyosó', '48001100025', 0, '[2,3,4]')
) as v(map_id, segment_id, name, room_id, room_type, neighbors)
on conflict (entity_id, map_id, segment_id) do update set
  name = excluded.name,
  room_id = excluded.room_id,
  room_type = excluded.room_type,
  neighbors = excluded.neighbors,
  is_active = true,
  updated_at = now();

commit;
