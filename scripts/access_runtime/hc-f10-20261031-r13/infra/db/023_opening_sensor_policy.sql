begin;

create table if not exists hc.opening_sensor_policy (
  entity_id bigint primary key references hc.entity(id) on delete cascade,
  opening_type text not null default 'window' check (opening_type in ('window', 'door')),
  updated_at timestamptz not null default now()
);

insert into hc.opening_sensor_policy (entity_id, opening_type, updated_at)
select e.id, 'window', now()
from hc.entity e
join hc.device d on d.id = e.device_id
where d.ext_id in (
  '0xa4c13813bb96142a',
  '0xa4c138e8978f6832'
)
on conflict (entity_id) do update set
  opening_type = excluded.opening_type,
  updated_at = now();

commit;
