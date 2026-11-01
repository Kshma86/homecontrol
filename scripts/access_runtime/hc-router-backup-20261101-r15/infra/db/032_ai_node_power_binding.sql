insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'ai_node_power_plug', e.id, now()
from hc.entity e
join hc.device d on d.id = e.device_id
join hc.power_wall_policy wp on wp.entity_id = e.id
where e.is_active = true
  and d.is_active = true
  and lower(wp.display_name) = 'ai szerver'
order by e.id
limit 1
on conflict (process_key) do nothing;
