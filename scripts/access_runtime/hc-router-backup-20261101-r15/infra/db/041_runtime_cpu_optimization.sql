-- Reduce high-frequency history writes while keeping current state fresh.
-- Current values continue to be maintained in hc.entity_state.

update hc.entity_metric
set min_interval_sec = 10
where metric_key = 'power_w'
  and min_interval_sec is not null
  and min_interval_sec < 10;

update hc.entity_metric
set min_interval_sec = 120,
    max_interval_sec = greatest(coalesce(max_interval_sec, 900), 900),
    deadband_num = greatest(coalesce(deadband_num, 1), 1)
where metric_key = 'voltage_v';

update hc.entity_metric
set max_interval_sec = 300
where entity_id = 24
  and metric_key in (
    'manual_valve_state',
    'pump_running',
    'valve_code',
    'valve_code_text',
    'valve_state'
  )
  and max_interval_sec is not null
  and max_interval_sec < 300;
