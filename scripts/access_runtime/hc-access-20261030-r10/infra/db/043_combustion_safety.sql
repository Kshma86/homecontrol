begin;

alter table hc.opening_sensor_policy
  add column if not exists extractor_air_role text not null default 'none';

alter table hc.opening_sensor_policy
  drop constraint if exists opening_sensor_policy_extractor_air_role_check;

alter table hc.opening_sensor_policy
  add constraint opening_sensor_policy_extractor_air_role_check
  check (extractor_air_role in ('none', 'secondary', 'primary'));

create table if not exists hc.combustion_safety_config (
  singleton boolean primary key default true check (singleton),
  enabled boolean not null default false,
  fan_on_w double precision not null default 50,
  fan_off_w double precision not null default 20,
  fan_on_seconds integer not null default 5,
  fan_off_seconds integer not null default 20,
  co_warning_ppm double precision not null default 10,
  co_shutdown_ppm double precision not null default 20,
  co_rise_ppm double precision not null default 2,
  auto_shutdown boolean not null default true,
  green_interval_seconds integer not null default 60,
  secondary_interval_seconds integer not null default 20,
  closed_interval_seconds integer not null default 4,
  pulse_seconds double precision not null default 1,
  updated_at timestamptz not null default now(),
  updated_by text not null default 'migration'
);

insert into hc.combustion_safety_config (singleton)
values (true)
on conflict (singleton) do nothing;

create table if not exists hc.combustion_safety_event (
  id bigserial primary key,
  ts timestamptz not null default now(),
  level text not null,
  event_type text not null,
  reason text not null default '',
  payload jsonb not null default '{}'::jsonb
);

create index if not exists ix_combustion_safety_event_ts
  on hc.combustion_safety_event (ts desc);

insert into hc.device (platform, ext_id, name, location, model, manufacturer, is_active)
values (
  'zigbee', '0xe8ca50e272a90000', 'Elszívó biztonsági jelző', 'Konyha',
  'CK-BL702-AL-01(7009_Z102LG03-1)', 'eWeLink', true
)
on conflict (platform, ext_id) do update set
  name = excluded.name,
  location = excluded.location,
  model = excluded.model,
  manufacturer = excluded.manufacturer,
  is_active = true,
  updated_at = now();

insert into hc.entity (device_id, name, topic_base, is_active)
select d.id, 'Elszívó biztonsági jelző', 'zigbee/0xe8ca50e272a90000', true
from hc.device d
where d.platform = 'zigbee' and d.ext_id = '0xe8ca50e272a90000'
  and not exists (select 1 from hc.entity e where e.device_id = d.id);

update hc.entity e
set name = 'Elszívó biztonsági jelző',
    topic_base = 'zigbee/0xe8ca50e272a90000',
    is_active = true
from hc.device d
where e.device_id = d.id
  and d.platform = 'zigbee'
  and d.ext_id = '0xe8ca50e272a90000';

insert into hc.metric (key, value_type, description, enforce_validation, is_active)
values
  ('brightness', 'num', 'Light brightness', false, true),
  ('color', 'json', 'Light colour payload', false, true),
  ('color_temp', 'num', 'Light colour temperature', false, true)
on conflict (key) do update set is_active = true;

insert into hc.metric (key, value_type, description, enforce_validation, is_active)
values ('switch_state', 'bool', 'Switch on/off state', false, true)
on conflict (key) do update set is_active = true;

with bulb as (
  select e.id entity_id from hc.entity e join hc.device d on d.id=e.device_id
  where d.platform='zigbee' and d.ext_id='0xe8ca50e272a90000'
), metric_seed(metric_key, store_mode) as (
  values ('switch_state','both'),('brightness','state'),('color','state'),('color_temp','state'),('linkquality','state')
)
insert into hc.entity_metric(entity_id,metric_key,store_mode,is_enabled)
select bulb.entity_id, metric_seed.metric_key, metric_seed.store_mode, true from bulb cross join metric_seed
on conflict(entity_id,metric_key) do update set store_mode=excluded.store_mode,is_enabled=true;

insert into hc.process_sensor_binding(process_key, entity_id, updated_at)
select 'combustion_extractor', e.id, now() from hc.entity e
where e.topic_base='zigbee/0xa4c13812631a96d4'
on conflict(process_key) do update set entity_id=excluded.entity_id,updated_at=now();

insert into hc.process_sensor_binding(process_key, entity_id, updated_at)
select 'combustion_indicator', e.id, now() from hc.entity e
where e.topic_base='zigbee/0xe8ca50e272a90000'
on conflict(process_key) do update set entity_id=excluded.entity_id,updated_at=now();

insert into hc.process_sensor_binding(process_key, entity_id, updated_at)
select 'combustion_co_sensor', e.id, now() from hc.entity e
where e.topic_base='zigbee/0xa4c1386ab8457e91'
on conflict(process_key) do update set entity_id=excluded.entity_id,updated_at=now();

insert into hc.process_sensor_binding(process_key, entity_id, updated_at)
values ('combustion_smoke_sensor', null, now())
on conflict(process_key) do nothing;

update hc.opening_sensor_policy osp
set extractor_air_role='primary', updated_at=now()
from hc.entity e
where osp.entity_id=e.id and e.topic_base='zigbee/0xa4c138e8978f6832';

commit;
