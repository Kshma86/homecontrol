"""Bounded inputs for the existing daily formulas (HC-14).

Keep all rows at the last timestamp preceding the window for interval metrics.
This preserves five-minute carry-in, timestamp ties, day splitting and DST.
Point metrics use only in-window input. No persisted schema is changed.
"""

DAILY_FORMULAS = {
    'irrigation_daily_energy': """with current_samples as (
  select
    ts,
    greatest(v_num, 0) as current_a,
    lead(ts) over (order by ts) as next_ts
  from hc.measurement
  where key = 'pump_current_a'
),
current_intervals as (
  select
    ts as start_ts,
    least(coalesce(next_ts, ts), ts + interval '5 minutes') as end_ts,
    current_a
  from current_samples
),
current_by_day as (
  select
    g.day_start::date as day,
    current_a,
    extract(epoch from least(end_ts, g.day_start + interval '1 day') - greatest(start_ts, g.day_start)) as seconds
  from current_intervals
  cross join lateral generate_series(
    date_trunc('day', start_ts),
    date_trunc('day', end_ts),
    interval '1 day'
  ) as g(day_start)
  where end_ts > start_ts
    and least(end_ts, g.day_start + interval '1 day') > greatest(start_ts, g.day_start)
),
daily_current as (
  select
    day,
    count(*) as current_samples,
    round(avg(current_a)::numeric, 3) as avg_current_a,
    round(max(current_a)::numeric, 3) as max_current_a,
    round((sum(seconds) / 3600.0)::numeric, 3) as measured_hours,
    round((sum(case when current_a > 0.05 then seconds else 0 end) / 60.0)::numeric, 1) as active_minutes,
    round((sum(current_a * seconds) / 3600.0)::numeric, 3) as amp_hours
  from current_by_day
  group by day
),
daily_voltage as (
  select
    date_trunc('day', ts)::date as day,
    count(*) as voltage_samples,
    round(avg(v_num)::numeric, 3) as avg_voltage_v
  from hc.measurement
  where key = 'supply_voltage_12v'
  group by date_trunc('day', ts)::date
)
select
  c.day,
  c.current_samples,
  c.avg_current_a,
  c.max_current_a,
  c.measured_hours,
  c.active_minutes,
  c.amp_hours,
  v.voltage_samples,
  v.avg_voltage_v,
  round((c.amp_hours * v.avg_voltage_v)::numeric, 2) as watt_hours
from daily_current c
left join daily_voltage v on v.day = c.day""",
    'irrigation_pump_daily': """with samples as (
  select
    ts,
    coalesce(v_bool, false) as pump_running,
    lead(ts) over (order by ts) as next_ts
  from hc.measurement
  where key = 'pump_running'
),
intervals as (
  select
    ts as start_ts,
    least(coalesce(next_ts, ts), ts + interval '5 minutes') as end_ts,
    pump_running
  from samples
),
by_day as (
  select
    g.day_start::date as day,
    pump_running,
    extract(epoch from least(end_ts, g.day_start + interval '1 day') - greatest(start_ts, g.day_start)) as seconds
  from intervals
  cross join lateral generate_series(
    date_trunc('day', start_ts),
    date_trunc('day', end_ts),
    interval '1 day'
  ) as g(day_start)
  where end_ts > start_ts
    and least(end_ts, g.day_start + interval '1 day') > greatest(start_ts, g.day_start)
)
select
  day,
  round((sum(case when pump_running then seconds else 0 end) / 60.0)::numeric, 1) as pump_running_minutes,
  round((sum(seconds) / 3600.0)::numeric, 3) as measured_hours,
  count(*) as state_samples
from by_day
group by day""",
    'irrigation_solar_daily': """with charge_samples as (
  select
    ts,
    greatest(v_num, 0) as current_a,
    lead(ts) over (order by ts) as next_ts
  from hc.measurement
  where key = 'solar_charge_current_a'
),
charge_intervals as (
  select
    ts as start_ts,
    least(coalesce(next_ts, ts), ts + interval '5 minutes') as end_ts,
    current_a
  from charge_samples
),
charge_by_day as (
  select
    g.day_start::date as day,
    current_a,
    extract(epoch from least(end_ts, g.day_start + interval '1 day') - greatest(start_ts, g.day_start)) as seconds
  from charge_intervals
  cross join lateral generate_series(
    date_trunc('day', start_ts),
    date_trunc('day', end_ts),
    interval '1 day'
  ) as g(day_start)
  where end_ts > start_ts
    and least(end_ts, g.day_start + interval '1 day') > greatest(start_ts, g.day_start)
),
metric_daily as (
  select
    date_trunc('day', ts)::date as day,
    round(avg(v_num) filter (where key = 'solar_battery_voltage_v')::numeric, 3) as avg_battery_voltage_v,
    round(min(v_num) filter (where key = 'solar_battery_voltage_v')::numeric, 3) as min_battery_voltage_v,
    round(max(v_num) filter (where key = 'solar_battery_voltage_v')::numeric, 3) as max_battery_voltage_v,
    round(avg(v_num) filter (where key = 'solar_charge_current_a')::numeric, 3) as avg_charge_current_a,
    round(max(v_num) filter (where key = 'solar_charge_current_a')::numeric, 3) as max_charge_current_a,
    round(avg(v_num) filter (where key = 'solar_pv_voltage_v')::numeric, 3) as avg_pv_voltage_v,
    round(max(v_num) filter (where key = 'solar_pv_voltage_v')::numeric, 3) as max_pv_voltage_v,
    round(avg(v_num) filter (where key = 'solar_pv_current_a')::numeric, 3) as avg_pv_current_a,
    round(max(v_num) filter (where key = 'solar_pv_current_a')::numeric, 3) as max_pv_current_a,
    round(avg(v_num) filter (where key = 'solar_controller_temp_c')::numeric, 2) as avg_solar_controller_temp_c,
    round(max(v_num) filter (where key = 'solar_controller_temp_c')::numeric, 2) as max_solar_controller_temp_c,
    count(*) as samples
  from hc.measurement
  where key in (
    'solar_battery_voltage_v',
    'solar_charge_current_a',
    'solar_pv_voltage_v',
    'solar_pv_current_a',
    'solar_controller_temp_c'
  )
  group by date_trunc('day', ts)::date
),
charge_daily as (
  select
    day,
    round((sum(current_a * seconds) / 3600.0)::numeric, 3) as charge_amp_hours,
    round((sum(seconds) / 3600.0)::numeric, 3) as measured_hours
  from charge_by_day
  group by day
)
select
  m.*,
  c.charge_amp_hours,
  c.measured_hours
from metric_daily m
left join charge_daily c on c.day = m.day""",
    'irrigation_controller_temp_daily': """select
  date_trunc('day', ts)::date as day,
  round(avg(v_num)::numeric, 2) as avg_controller_temp_c,
  round(min(v_num)::numeric, 2) as min_controller_temp_c,
  round(max(v_num)::numeric, 2) as max_controller_temp_c,
  count(*) as samples
from hc.measurement
where key = 'controller_temp_c'
group by date_trunc('day', ts)::date""",
    'irrigation_tank_daily': """select
  date_trunc('day', ts)::date as day,
  round(avg(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as avg_level_percent,
  round(min(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as min_level_percent,
  round(max(v_num) filter (where key = 'liquid_level_percent')::numeric, 2) as max_level_percent,
  round(avg(v_num) filter (where key = 'liquid_depth')::numeric, 3) as avg_depth_m
from hc.measurement
where key in ('liquid_level_percent', 'liquid_depth')
group by date_trunc('day', ts)::date""",
}

INPUT_KEYS = {'irrigation_daily_energy': (['pump_current_a', 'supply_voltage_12v'], ['pump_current_a']), 'irrigation_pump_daily': (['pump_running'], ['pump_running']), 'irrigation_solar_daily': (['solar_battery_voltage_v', 'solar_charge_current_a', 'solar_pv_voltage_v', 'solar_pv_current_a', 'solar_controller_temp_c'], ['solar_charge_current_a']), 'irrigation_controller_temp_daily': (['controller_temp_c'], []), 'irrigation_tank_daily': (['liquid_level_percent', 'liquid_depth'], [])}

def bounded_daily_query(name, days):
    days = max(14, int(days))
    point_keys, interval_keys = INPUT_KEYS[name]
    literal = lambda values: ", ".join("'" + key + "'" for key in values)
    boundary = ""
    if interval_keys:
        values = ", ".join("('" + key + "')" for key in interval_keys)
        boundary = f"""
        union all
        select m.* from (values {values}) as keys(key)
        cross join lateral (
          select max(ts) as ts from hc.measurement
          where key = keys.key and ts < (select cutoff from summary_window)
        ) previous
        join hc.measurement m on m.key = keys.key and m.ts = previous.ts
        """
    formula = DAILY_FORMULAS[name].replace('hc.measurement', 'summary_input')
    return f"""
    with summary_window as (
      select (current_date - ({days}::int - 1))::timestamptz as cutoff
    ), summary_input as materialized (
      select * from hc.measurement
      where key in ({literal(point_keys)}) and ts >= (select cutoff from summary_window)
      {boundary}
    )
    select * from ({formula}) daily
    where day >= current_date - ({days}::int - 1)
    """
