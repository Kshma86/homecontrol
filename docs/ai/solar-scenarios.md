# Solar Scenarios And Eval Cases

## Missing Growatt Entity

Given:

- No active entity has topic base `homecontrol/tele/growatt/cloud`.

Expected:

- `GET /api/context/solar` returns `ok: false`.
- Error identifies the missing Growatt cloud entity.
- No write or MQTT publish is attempted.

## Current Values

Given:

- `entity_state` contains several Growatt keys.

Expected:

- `state` contains all available state rows keyed by metric.
- `current` contains only the prioritized dashboard values.
- `summary.state_count` equals the number of state rows.
- `summary.updated_at` is the latest state timestamp.

## 24 Hour Charts

Given:

- Measurements exist for `local_load_power_w` in the last 24 hours.

Expected:

- `charts.load_power_24h` contains hourly buckets.
- Empty hours are present with `sample_count = 0`.

## 30 Day Production

Given:

- Measurements contain daily production counters.

Expected:

- `charts.production_daily_30d` contains 30 date rows.
- Production uses `energy_today_kwh`, then `plant_energy_today_kwh`, then
  `solar_energy_today_kwh` fallback order.

## Suggested Tests

- Missing entity returns a non-throwing `ok: false` payload.
- Current priority list includes newly added metrics.
- Empty measurement periods still emit fixed chart buckets.
