# Irrigation Domain Context

This file is the canonical AI-facing contract for the HomeControl irrigation
module.

## Scope

The irrigation module controls and observes garden watering through:

- An ESP irrigation controller.
- A motorized valve.
- A pump state/current telemetry stream.
- A manual valve sensor/state.
- Tank level telemetry.
- Soil moisture sensors.
- A Zigbee rain sensor.
- OpenWeather observations and forecast snapshots.
- Legacy and V2 scheduler execution paths.
- A pilot/navigator rule engine that can recommend or apply watering duration.

Primary implementation:

- `infra/backend/irrigation_service.py`
- `infra/backend/api_route_modules.py`
- `infra/backend/app.py`
- `infra/backend/scheduler_service.py`
- `infra/db/001_irrigation_admin.sql`
- `infra/db/004_v2_irrigation_plan_shadow_backfill.sql`
- `infra/db/005_v2_irrigation_execution_shadow_backfill.sql`
- `infra/backend/tests/test_irrigation_service.py`

## Core Safety Principles

- Only one irrigation session may be `running` or `starting` at a time.
- A scheduled run must not start when the manual valve guard is blocked.
- A physical open/close command must be confirmed from live valve telemetry.
- Failed open confirmation results in `start_failed`, not `running`.
- Failed stop confirmation results in `stop_failed`, and the schedule should not
  be marked stopped.
- A session that reports both motorized and manual valves as closed after a
  startup grace period is failed as `failed_no_watering`.
- Every session has a requested stop time and a hard safety stop time.
- Duration is clamped to `IRRIGATION_MANUAL_MAX_MINUTES`.
- Shadow/audit records must not publish device commands.

## Environment And Defaults

Configured in `infra/backend/app.py`:

- `IRRIGATION_DEVICE_ID`: default `esp-irrigation-1`
- `IRRIGATION_MANUAL_MAX_MINUTES`: default `180`
- `IRRIGATION_SNAPSHOT_CACHE_TTL`: default `10`
- `IRRIGATION_PILOT_CACHE_TTL`: default `300`
- `IRRIGATION_WEATHER_SUMMARY_CACHE_TTL`: default `300`
- `IRRIGATION_DAILY_SUMMARY_DAYS`: default `200`
- `IRRIGATION_DAILY_SUMMARY_REFRESH_SEC`: default `300`
- `IRRIGATION_SCHEDULER_POLL_SECONDS`: default `5`
- `IRRIGATION_STOP_CONFIRM_ATTEMPTS`: default `3`
- `IRRIGATION_STOP_REACTION_DELAY_SECONDS`: default `5`
- `IRRIGATION_STOP_CLOSED_DELAY_SECONDS`: default `30`
- `IRRIGATION_OPEN_CONFIRM_ATTEMPTS`: default `3`
- `IRRIGATION_OPEN_REACTION_DELAY_SECONDS`: default `5`
- `IRRIGATION_OPEN_READY_DELAY_SECONDS`: default `30`
- `OPENWEATHER_API_KEY`
- `OPENWEATHER_LAT`
- `OPENWEATHER_LON`
- `OPENWEATHER_UNITS`: default `metric`
- `OPENWEATHER_LANG`: default `hu`
- `OPENWEATHER_POLL_SECONDS`: default `3600`

V2 execution flags:

- `HC_V2_EXECUTION_ENABLED`
- `HC_V2_EXECUTION_ALLOW_IRRIGATION`
- scheduler mode must include irrigation publishing, such as
  `v2_execute_irrigation` or `v2_execute_all` depending on current schema/code.

## MQTT Topics

Command base:

```text
homecontrol/cmd/irrigation/{IRRIGATION_DEVICE_ID}
```

Command topics:

- `.../valve`
- `.../system`
- `.../mode`
- `.../pump`
- `.../config`

Telemetry topics:

- `homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/pump_metrics`
- `homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/nano_status`
- `homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/diag`
- `homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/nano_cfg`
- `homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/nano_event`
- `homecontrol/tele/irrigation/{IRRIGATION_DEVICE_ID}/solar`
- `homecontrol/stat/irrigation/{IRRIGATION_DEVICE_ID}/availability`
- `homecontrol/stat/irrigation/{IRRIGATION_DEVICE_ID}/cmd_ack`

Known Zigbee topics used by the irrigation read model:

- `zigbee/0xa4c13880b130079c`: tank level.
- `zigbee/0xa4c138479ed598c1`: rain sensor.
- `zigbee/0xa4c13844a0908898`: `Moisture_02`.
- `zigbee/0xa4c1382abf3f8730`: additional irrigation sensor currently read by
  the snapshot builder.

## Command Payloads

Open valve:

```json
{
  "cmd": "set",
  "value": "open",
  "source": "homecontrol-admin",
  "duration_minutes": 20
}
```

Close valve:

```json
{
  "cmd": "set",
  "value": "close",
  "reason": "manual_stop"
}
```

Stop command reasons in current code:

- `manual_stop`
- `manual_command`
- `auto_timeout`
- `schedule_stop`
- `v2_effective_stop`

Direct command names accepted by `/api/irrigation/command`:

- `valve_close`
- `valve_stop`
- `valve_home`
- `valve_status`
- `valve_cal_zero`
- `fault_reset`
- `diag_now`
- `nano_status_now`
- `ping`
- `mode_auto`
- `mode_manual`
- `pump_on`
- `pump_off`
- `nano_get`
- `nano_save`
- `nano_load`
- `nano_defaults`

Nano config command:

```json
{
  "cmd": "nano_set",
  "key": "...",
  "value": "..."
}
```

## API Endpoints

Mutation endpoints:

- `POST /api/irrigation/manual/start`
- `POST /api/irrigation/manual/stop`
- `POST /api/irrigation/command`
- `POST /api/irrigation/nano-config`
- `PUT /api/irrigation/schedules/<schedule_id>`
- `PUT /api/irrigation/pilot/config`
- `POST /api/irrigation/pilot/evaluate`
- `POST /api/irrigation/weather/fetch`

Read endpoints:

- `GET /api/context/irrigation`
- `GET /api/context/irrigation_pilot`
- `GET /api/context/irrigation_statistics`
- `GET /api/irrigation/state`
- `GET /api/irrigation/pilot`
- `GET /api/irrigation/statistics`

Mutation responses should return a `context.read_after` hint for the affected
sections.

## Database Objects

Important durable tables:

- `hc.irrigation_manual_session`
- `hc.irrigation_schedule`
- `hc.irrigation_pilot_config`
- `hc.irrigation_pilot_decision`
- `hc.weather_observation`
- `hc.event`
- `hc.plan`
- `hc.execution`

Summary/cache tables created by `IrrigationService.ensure_summary_schema()`:

- `hc.irrigation_daily_energy_summary`
- `hc.irrigation_pump_daily_summary`
- `hc.irrigation_solar_daily_summary`
- `hc.irrigation_tank_daily_summary`
- `hc.irrigation_controller_temp_daily_summary`

Important views referenced by the service:

- `hc.irrigation_daily_energy`
- `hc.irrigation_pump_daily`
- `hc.irrigation_solar_daily`
- `hc.irrigation_tank_daily`
- `hc.irrigation_controller_temp_daily`
- `hc.irrigation_session_stats`

## Session Lifecycle

Statuses currently used:

- `starting`: row inserted, open command is being confirmed.
- `running`: open command confirmed.
- `stopped`: manually stopped with successful close confirmation.
- `auto_stopped`: automatically stopped with successful close confirmation.
- `stop_failed`: close command was not confirmed.
- `start_failed`: open command was not confirmed.
- `failed_no_watering`: controller accepted/start session exists, but physical
  telemetry indicates no watering after the grace period.

Manual start flow:

1. Clamp requested `duration_minutes` to `1..IRRIGATION_MANUAL_MAX_MINUTES`.
2. Reject with HTTP `409` if a `running` or `starting` session exists.
3. Insert `hc.irrigation_manual_session` with status `starting`.
4. Publish open command and confirm valve state.
5. On confirmation, update session to `running`, store confirmation details, and
   invalidate `irrigation`.
6. On failure, update session to `start_failed`, store error details, and return
   HTTP `502`.

Manual stop flow:

1. If no `session_id` is provided, use the latest `running` session.
2. Return HTTP `404` if no running session exists.
3. Publish close command with reason `manual_stop`.
4. On confirmation, status becomes `stopped`.
5. On failure, status becomes `stop_failed`.
6. Invalidate `irrigation`.

Safety worker behavior:

- `stop_overdue_sessions()` closes sessions whose `requested_stop_at` or
  `safety_stop_at` has passed.
- `fail_sessions_without_physical_watering()` marks old running sessions as
  `failed_no_watering` when both motorized and manual valves are reported
  closed.

## Valve Confirmation

Live valve state is read from the MQTT monitor snapshot. The service prefers
JSON payloads from:

- `pump_metrics`
- `esp_nano_status`

Open confirmation:

- success if motorized valve is exactly `OPEN`;
- reaction is considered seen if valve text contains `OPEN`, `OPENING`,
  `BETWEEN`, `MOVING_OPEN`, or current is above `0.01 A`;
- each attempt publishes the command, waits the configured reaction/ready
  delays, and records observed states.

Close confirmation:

- success if valve text contains `CLOSED`;
- reaction is considered seen if valve text indicates closed/closing or current
  is above `0.01 A`;
- each attempt publishes the command, waits the configured reaction/closed
  delays, and records observed states.

Manual valve guard:

- Reads latest `manual_valve_state` from the ESP irrigation entity.
- Blocks scheduled starts when state contains `OPEN`, `OPENING`, `BETWEEN`, or
  `MOVING`.
- Does not block when state contains `CLOSED`.

## Schedule Rules

`hc.irrigation_schedule` has one row per weekday:

- `day_of_week` is `0..6`.
- The code maps current day using `extract(isodow from now())::int - 1`, so
  Monday is `0` and Sunday is `6`.
- `start_time` must be before `stop_time`.
- Active schedules are eligible only on their configured day.
- A schedule starts only when local time is within `[start_time, stop_time)`.
- `last_started_on` prevents repeated starts on the same date.
- `last_stopped_on` prevents repeated stop handling on the same date.
- Updating today's active schedule resets `last_started_on` and
  `last_stopped_on` when start/stop/active values changed.

Schedule status values emitted by `fetch_schedules()`:

- `due_now`
- `attempted_today`
- `done_today`
- `armed_today`
- `armed`
- `disabled`

Legacy scheduled start:

1. `run_due_schedules()` checks the manual valve guard.
2. It selects due active rows ordered by `start_time, id`.
3. `start_scheduled_session()` rejects if another session is `running` or
   `starting`.
4. It evaluates the pilot rules.
5. It always marks `last_started_on = current_date` before command execution.
6. In `navigator` mode, pilot decision is logged as `navigator_only`, but
   scheduled duration remains authoritative.
7. In `pilot` mode, `final_duration <= 0` means skip watering and log
   `skipped`.
8. Otherwise it opens the valve, creates a session, and stores confirmation.

Legacy scheduled stop:

- Runs when local time is at or after `stop_time`, the schedule started today,
  and it has not been stopped today.
- Finds today's matching `scheduler` or `pilot` session.
- If session is `running`, publishes close with reason `schedule_stop`.
- Does not mark schedule stopped when the session is `stop_failed`.
- Marks stopped when there is no session, or session status is already
  `stopped`/`auto_stopped`.

## Pilot And Navigator

Pilot config fields:

- `mode`: `navigator` or `pilot`
- `base_duration_minutes`
- `rain_24h_threshold_mm`
- `forecast_rain_threshold_mm`
- `pop_threshold_percent`
- `heat_threshold_c`
- `heat_correction_percent`
- `cold_threshold_c`
- `cold_correction_percent`
- `soil_moisture_enabled`
- `soil_sensor_topic_base`: default `zigbee/0xa4c13844a0908898` (`Moisture_02`)
- `soil_wet_skip_threshold_percent`
- `soil_dry_threshold_percent`
- `soil_dry_correction_percent`
- `soil_sample_max_age_hours`

Modes:

- `navigator`: calculate and log recommendation, but do not change scheduled
  watering duration.
- `pilot`: apply the calculated `final_duration`; may skip watering.

Analysis rule for AI:

- Always connect `irrigation.schedules`, `irrigation.sessions` or
  `irrigation.analysis.cycles`, `irrigation_pilot`, and `scheduler` when
  explaining watering behavior.
- `irrigation_pilot.config.mode` tells whether active rules are advisory
  (`navigator`) or execution-affecting (`pilot`).
- Active pilot rules are visible in `recommendation.triggered_rules`,
  `latest_decision.triggered_rules`, `today_decision.triggered_rules`, and the
  corresponding `reason`.
- `execution_status` tells how far the decision got: recommendation only,
  skipped, command confirmed, start failed, stop failed, completed, and so on.
- `scheduler.engine.publish_domains` and `scheduler.engine.command_owner` tell
  whether V2 may actually publish irrigation commands.
- Session `start_payload` may contain `pilot_final_duration`,
  `pilot_triggered_rules`, `pilot_reason`, `hc_executor`, and `stop_policy`;
  use these to link a concrete watering cycle back to scheduler/pilot intent.
- Do not say "the pilot watered" only because a recommendation exists. In
  `navigator` mode the recommendation is advisory; real watering still follows
  schedule duration unless another command path is present.

Base duration source:

- Scheduler execution passes the schedule duration as `base_duration`.
- Manual pilot evaluation uses the nearest active schedule if available.
- If no active schedule is available, it falls back to
  `base_duration_minutes`.

Rule order:

1. If rain in the last 24 hours is greater than
   `rain_24h_threshold_mm`, set `final_duration = 0` and trigger
   `rain_skip`.
2. Else if precipitation probability is greater than
   `pop_threshold_percent` and forecast rain is greater than
   `forecast_rain_threshold_mm`, set `final_duration = 0` and trigger
   `forecast_skip`.
3. Else if enabled `Moisture_02` soil moisture is fresh and greater than
   `soil_wet_skip_threshold_percent`, set `final_duration = 0` and trigger
   `soil_wet_skip`.
4. Else if enabled `Moisture_02` soil moisture is fresh and less than
   `soil_dry_threshold_percent`, apply `soil_dry_correction_percent` and
   trigger `soil_dry_increase`.
5. Else if expected temperature is greater than `heat_threshold_c`, apply
   `heat_correction_percent` and trigger `heat_increase`.
6. Else if expected temperature is less than `cold_threshold_c`, apply
   `cold_correction_percent` and trigger `cold_decrease`.
7. Else keep the base duration unchanged.

Comparison operators are strict `>` and `<`, not inclusive.

Duration corrections are rounded with Python `round()` and then clamped to at
least `1` minute. Skip rules are the only normal path to `0`.

Weather snapshot inputs:

- OpenWeather current/forecast observations.
- Aggregated rain over the last 24 hours.
- Outdoor local temperature/humidity sensor named `Udvar`.
- Zigbee rain sensor wet/dry, last wet timestamp, battery, and link quality.
- Garden soil moisture from `Moisture_02`, including latest percentage,
  sample age, and 24h min/avg/max. Stale samples are logged but ignored.

Pilot decision execution statuses currently used:

- `not_executed`
- `manual_evaluation`
- `navigator_only`
- `skipped`
- `command_sent`
- `command_confirmed`
- `completed`
- `stop_failed`
- `no_physical_watering`
- `start_failed`
- `v2_skipped`
- `v2_command_confirmed`
- `v2_start_failed`

## V2 Irrigation Execution

V2 scheduler audit creates `hc.event`, `hc.plan`, and `hc.execution` rows.
Shadow/audit rows use `side_effects: false` and must not publish commands.

V2 execution path:

- `IrrigationService.scheduler_tick()` only runs when the scheduler engine
  includes `irrigation` in `publish_domains`.
- `run_v2_due_schedules()` follows the same manual valve guard and due-schedule
  selection as legacy.
- `start_v2_scheduled_session()` creates sessions with
  `started_by = 'v2_scheduler'`.
- V2 uses a single effective stop policy.
- In `pilot` mode, the effective stop time is based on `final_duration`.
- In `navigator` mode, the scheduled duration remains authoritative.
- V2 stop uses `requested_stop_at` for sessions created by `v2_scheduler` and
  publishes close with reason `v2_effective_stop`.

`stop_policy` fields:

- `stop_authority`
- `scheduled_start`
- `scheduled_stop`
- `scheduled_duration_minutes`
- `effective_duration_minutes`
- `effective_stop_at`
- `rule_engine_mode`
- `rule_engine_reason`
- `triggered_rules`
- `legacy_requested_stop_at_is_diagnostic`

Preflight checks for irrigation include:

- scheduler mode requests irrigation execution;
- V2 execution feature flag enabled;
- irrigation publish flag enabled;
- database connectivity;
- MQTT connectivity;
- manual valve guard not blocked;
- no active irrigation session;
- recent V2 audit chains available and matching when possible;
- historical stop timing drift warnings.

## Context Payload

`GET /api/context/irrigation` includes:

- `manual_max_minutes`
- `live`
- `latest`
- `soil_moisture_24h`
- `sessions`
- `session_stats`
- `scheduler_guard`
- `schedules`
- `energy_daily`
- `pump_daily`
- `solar_daily`
- `temp_daily`
- `tank_daily`

`GET /api/context/irrigation_pilot` includes:

- `config`
- `weather`
- `recommendation`
- `latest_decision`
- `today_decision`
- last 50 `decisions`

`GET /api/context/ai/summary` includes a compact `irrigation_pilot` block with:

- `config`
- `recommendation`
- `latest_decision`
- `today_decision`

This compact block is the preferred source for answering "which active
scheduler/pilot rules affected watering?" questions.

`GET /api/context/irrigation_statistics` includes:

- `tank_24h`
- `soil_moisture_24h`
- `tank_daily`
- `pump_daily`
- `solar_daily`
- `temp_daily`
- recent session statistics

## Editing Guidance

- If you change session lifecycle, update tests for start, stop, failed open,
  failed close, and no-physical-watering behavior.
- If you change scheduler timing, test one-run-per-day and stop marking rules.
- If you change pilot rules, test rule precedence and threshold equality.
- If you add an MQTT command, document topic, payload, and context invalidation.
- If you add telemetry, register metrics and decide whether it belongs in
  `latest`, daily summaries, `irrigation_statistics`, or `irrigation_pilot`.
- If you change V2 behavior, verify shadow records still have no side effects
  unless V2 publish flags explicitly allow execution.
