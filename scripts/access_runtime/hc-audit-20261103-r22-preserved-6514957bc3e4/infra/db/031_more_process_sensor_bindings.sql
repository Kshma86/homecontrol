insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'climate_power_meter', e.id, now()
from hc.entity e
join hc.device d on d.id = e.device_id
where d.ext_id = 'bf7bda0d19d3934720scjs'
  and e.is_active = true
  and d.is_active = true
order by e.id
limit 1
on conflict (process_key) do nothing;

insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'climate_extra_fan_socket', e.id, now()
from hc.power_wall_policy wp
join hc.entity e on e.id = wp.entity_id
join hc.device d on d.id = e.device_id
where wp.auto_climate = true
  and e.is_active = true
  and d.is_active = true
order by e.name
limit 1
on conflict (process_key) do nothing;

insert into hc.process_sensor_binding (process_key, entity_id, updated_at)
select 'hc_server_power_meter', e.id, now()
from hc.entity e
join hc.device d on d.id = e.device_id
left join hc.power_wall_policy wp on wp.entity_id = e.id
where e.is_active = true
  and d.is_active = true
  and d.platform = 'tuya'
  and (
    wp.display_name = 'HC szerver'
    or d.ext_id = 'bf6ac883a687a6a2a2ci8l'
    or lower(e.name) = 'hc szerver'
  )
order by
  case
    when wp.display_name = 'HC szerver' then 0
    when d.ext_id = 'bf6ac883a687a6a2a2ci8l' then 1
    else 2
  end,
  e.id
limit 1
on conflict (process_key) do nothing;
