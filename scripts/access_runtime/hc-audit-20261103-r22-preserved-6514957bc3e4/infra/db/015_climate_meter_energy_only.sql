begin;

delete from hc.entity_metric em
using hc.entity e
join hc.device d on d.id = e.device_id
where em.entity_id = e.id
  and d.platform = 'tuya'
  and d.ext_id = 'bf7bda0d19d3934720scjs'
  and em.metric_key in ('power_w', 'current_a');

delete from hc.entity_state s
using hc.entity e
join hc.device d on d.id = e.device_id
where s.entity_id = e.id
  and d.platform = 'tuya'
  and d.ext_id = 'bf7bda0d19d3934720scjs'
  and s.key in ('power_w', 'current_a');

delete from hc.measurement m
using hc.entity e
join hc.device d on d.id = e.device_id
where m.entity_id = e.id
  and d.platform = 'tuya'
  and d.ext_id = 'bf7bda0d19d3934720scjs'
  and m.key in ('power_w', 'current_a');

commit;
