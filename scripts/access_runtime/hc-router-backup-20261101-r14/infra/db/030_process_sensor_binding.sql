create table if not exists hc.process_sensor_binding (
  process_key text primary key,
  entity_id bigint references hc.entity(id) on delete set null,
  updated_at timestamptz not null default now()
);

create index if not exists ix_process_sensor_binding_entity
  on hc.process_sensor_binding (entity_id);

insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'irrigation_soil_moisture', e.id, now()
from hc.entity e
where e.topic_base = 'zigbee/0xa4c13844a0908898'
on conflict (process_key) do nothing;

insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'marten_power_socket', e.id, now()
from hc.entity e
where lower(e.name) like '%nyestriaszt%'
order by e.name
limit 1
on conflict (process_key) do nothing;
