# Climate Scenarios And Eval Cases

## Empty Command Refresh

Given:

- `/api/climate/gree/command` receives an empty JSON body.

Expected:

- Publish `{"refresh": true}`.
- Invalidate `climate` and `power_wall`.

## Invalid Power

Given:

- Command contains `power: "maybe"`.

Expected:

- Reject with validation error.
- Do not publish MQTT.

## Valid Power On

Given:

- Command contains `power: "on"`.
- MQTT publish succeeds.

Expected:

- Publish to the climate command topic.
- Run power-wall auto climate sync.
- Include `auto_power_wall` results in response.
- Invalidate `climate` and `power_wall`.

## Invalid Temperature

Given:

- Command contains `target_temperature: 31`.

Expected:

- Reject with `target_temperature must be between 8 and 30`.
- Do not publish.

## Schedule Create

Given:

- Valid schedule payload with day, time, power, mode, target temperature, fan,
  and light.

Expected:

- Insert `hc.climate_schedule_rule`.
- Return refreshed schedule list.
- Invalidate `climate_schedules`.

## Schedule Delete Missing

Given:

- Delete request references a non-existent schedule id.

Expected:

- Return not found behavior from route wrapper.
- Do not invalidate unless a row was actually deleted.

## Power Meter Missing

Given:

- `CLIMATE_POWER_METER_EXT_ID` is empty or unknown.

Expected:

- Climate state still returns.
- `power_meter.ok` is false.
- Power history returns `ok: false`.

## Climate Parameter History

Given:

- User asks how the climate is generally used or which settings are typical.
- `context.climate_history.ok` is true.

Expected:

- Answer from `climate_history` distributions and numeric summaries.
- Mention current settings from `climate`.
- Include schedule rules from `climate_schedules` only as configured intent, not
  as measured usage.
- Do not use room thermometer rows from `home_statistics` as AC settings.

## Suggested Tests

- Command validation rejects bad enum values.
- Empty command becomes refresh.
- Power command triggers auto power-wall sync only on successful publish.
- Schedule create/update/delete invalidates `climate_schedules`.
- Power scaling applies divisor exactly once.
- Parameter-history payload exposes latest power/mode/target/fan settings,
  24h/7d temperature summaries, 7d setting distributions, and recent setting
  changes.
