begin;

insert into hc.entity_metric (entity_id, metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec, is_enabled)
select e.id, 'power_w', 'both', 1::double precision, 5, 300, true
from hc.entity e
join hc.device d on d.id = e.device_id
where d.platform = 'tuya'
  and d.ext_id = 'bf7bda0d19d3934720scjs'
  and e.is_active = true
on conflict (entity_id, metric_key) do update set
  store_mode = excluded.store_mode,
  deadband_num = excluded.deadband_num,
  min_interval_sec = excluded.min_interval_sec,
  max_interval_sec = excluded.max_interval_sec,
  is_enabled = true;

commit;
