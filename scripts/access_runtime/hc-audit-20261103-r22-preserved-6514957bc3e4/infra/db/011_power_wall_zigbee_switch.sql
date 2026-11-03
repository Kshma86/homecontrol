begin;

insert into hc.metric (key, value_type, unit, min_num, max_num, description, enforce_validation, is_active)
values
  ('switch_state', 'bool', null, null, null, 'Switch on/off state', false, true)
on conflict (key) do update set
  value_type = excluded.value_type,
  unit = excluded.unit,
  min_num = excluded.min_num,
  max_num = excluded.max_num,
  description = excluded.description,
  enforce_validation = excluded.enforce_validation,
  is_active = true;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, 'switch_state', 'both', null::double precision, 1, 300, true
from hc.entity e
join hc.device d on d.id = e.device_id
where d.platform = 'zigbee'
  and e.is_active = true
  and exists (
    select 1
    from hc.entity_metric em
    where em.entity_id = e.id
      and em.metric_key in ('power', 'current', 'energy_kwh')
  )
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
