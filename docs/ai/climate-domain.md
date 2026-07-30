# Climate Domain Context

## Scope

The climate module controls a Gree climate bridge and reads an optional Tuya
power meter for climate energy/power history.

Primary implementation:

- `infra/backend/climate_service.py`
- `apps/gree-climate/gree_climate_bridge.py`
- `infra/backend/scheduler_service.py`
- `infra/db/014_climate_tuya_power_meter.sql`
- `infra/db/015_climate_meter_energy_only.sql`
- `infra/db/016_climate_meter_current_power.sql`
- `infra/db/026_gree_climate_parameter_history.sql`

## Ownership

- Command owner: `ClimateService.queue_command()`.
- Live state: MQTT monitor values from the Gree bridge.
- Parameter history truth: `hc.measurement` / `hc.entity_state` for the
  `gree_climate` entity at `homecontrol/gree_climate`.
- Durable schedule truth: `hc.climate_schedule_rule`.
- Power meter truth: Tuya entity state and measurements.
- Context sections: `climate`, `climate_power_history`,
  `climate_history`, `climate_schedules`.

## MQTT

Commands publish to:

```text
{CLIMATE_BASE_TOPIC}/command
```

The command payload may include:

- `power`: `on` or `off`
- `mode`: `auto`, `cool`, `dry`, `fan`, `heat`
- `target_temperature`: integer `8..30`
- `fan_speed`: `auto`, `low`, `mediumlow`, `medium`, `mediumhigh`, `high`
- `light`: `on` or `off`
- `refresh: true` when no command field is provided

## API Endpoints

Read endpoints:

- `GET /api/context/climate`
- `GET /api/context/climate_power_history`
- `GET /api/context/climate_history`
- `GET /api/context/climate_schedules`
- `GET /api/climate/gree/state`
- `GET /api/climate/gree/power-history`
- `GET /api/climate/gree/parameter-history`
- `GET /api/climate/gree/schedules`

Mutation endpoints:

- `POST /api/climate/gree/command`
- `POST /api/climate/gree/schedules`
- `PUT /api/climate/gree/schedules/<schedule_id>`
- `DELETE /api/climate/gree/schedules/<schedule_id>`

## Command Rules

- Invalid command values raise `ValueError`.
- Empty command body becomes a refresh command.
- Successful `power` on/off commands may trigger power-wall auto sync.
- Every queued command invalidates `climate` and `power_wall`.
- Response includes current state and `auto_power_wall` results.

## Schedule Rules

Schedule fields:

- `label`
- `day_of_week`: `0..6`
- `start_time`: `HH:MM`
- `is_enabled`
- `power`
- `mode`
- `target_temperature`
- `fan_speed`
- `light`
- `rule_engine`

Validation:

- `day_of_week` must be `0..6`.
- `start_time` must be `HH:MM`.
- `target_temperature` must be `8..30`.
- `power`, `mode`, `fan_speed`, and `light` must be known enum values.
- `rule_engine` defaults to manual schedule metadata.

Create/update/delete invalidates `climate_schedules`.

AI answer rule:

- For climate setting/parameter questions, use the live `climate` context and
  `climate_history`, then include `climate_schedules` when schedules matter.
- The live `climate` context gives the current `power`, `mode`,
  `target_temperature`, and `fan_speed`.
- `climate_history` gives historical Gree parameter usage: 24h/7d numeric
  summaries, 7d power/mode/fan distributions, recent setting changes, and
  sampled 24h values.
- `climate_schedules` gives configured scheduled settings.
- Do not infer AC settings from room thermometer sensors in `home_statistics`.
- Do not use Gree humidity fields for AI answers; the current bridge exposes
  dummy humidity values.
- If `climate_history.ok` is false or sample counts are low, say that the
  historical climate parameter data is still missing or warming up.

## Power Meter

The climate power meter is configured by `CLIMATE_POWER_METER_EXT_ID`.
In AI context this data is exposed as `climate_power`.

Important distinction:

- `climate_power` is the Gree climate/AC Tuya power meter.
- `server_power` is the HC server smart plug.
- Never answer climate consumption questions from `server_power`.
- Never answer HC server consumption questions from `climate_power`.

If not configured or not found:

- power meter payload returns `ok: false`;
- power-history payload also returns `ok: false`.

`power_w` is scaled by `CLIMATE_POWER_METER_DIVISOR`; divisor <= 0 falls back
to `1`.

Power history:

- last 24 hours of `power_w`;
- 30 daily rows of `energy_kwh`;
- summary includes sample counts, today energy, and max power.

## V2 Scheduler

Climate scheduler audit/execution lives in `SchedulerService`.

V2 climate execution:

- builds a climate command from scheduler payload;
- can publish only when the engine includes `climate` in `publish_domains`;
- if publish is blocked, execution remains shadow/audit;
- if command toggles power and auto sync is enabled, power-wall auto sync may
  run.

## Safety Rules

- Do not publish commands with out-of-range temperature.
- Do not invent unsupported fan or mode strings.
- Do not call power-wall sync unless a power command was actually accepted.
- Do not mutate climate schedule rows without invalidating
  `climate_schedules`.
