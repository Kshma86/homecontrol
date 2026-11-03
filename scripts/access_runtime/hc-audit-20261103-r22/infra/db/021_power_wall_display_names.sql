alter table hc.power_wall_policy
  add column if not exists display_name text;

insert into hc.power_wall_policy (entity_id, display_name, updated_at)
select e.id, 'HC szerver', now()
from hc.entity e
join hc.device d on d.id = e.device_id
where d.platform = 'tuya'
  and d.ext_id = 'bf6ac883a687a6a2a2ci8l'
  and e.is_active = true
on conflict (entity_id) do update set
  display_name = excluded.display_name,
  updated_at = now();
