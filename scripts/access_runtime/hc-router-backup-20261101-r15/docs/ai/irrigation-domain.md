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

- HC starts share one transactional admission gate: an existing `starting`,
  `running` or unresolved `stop_failed` session prevents a new reservation.
  Physical manual observations retain their separate tracking role.
- A scheduled run must not start when the manual valve guard is blocked.
- A physical open/close command must be confirmed from live valve telemetry.
- Failed open confirmation leaves `stop_failed` uncertainty until close is
  confirmed; only then does an interrupted/unconfirmed start become `start_failed`.
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
- `IRRIGATION_VALVE_TELE_MAX_AGE_SECONDS`: default `25`
- `IRRIGATION_VALVE_STATUS_MAX_AGE_SECONDS`: default `70`
- `IRRIGATION_NANO_ONLINE_MAX_AGE_SECONDS`: default `40`
- `IRRIGATION_START_RECOVERY_GRACE_SECONDS`: default `120` (never shorter
  than the configured nominal OPEN confirmation window plus 30 seconds)
- `IRRIGATION_RECOVERY_RETRY_SECONDS`: default `60`
- `IRRIGATION_RECOVERY_MAX_ATTEMPTS`: default `3` additional automatic CLOSE
  slots per session, persisted across process restarts
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
- `POST /api/irrigation/schedules`
- `PUT /api/irrigation/schedules/<schedule_id>`
- `DELETE /api/irrigation/schedules/<schedule_id>`
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

Tank statistics:

- `/api/irrigation/statistics` filters isolated upward tank level spikes from
  the chart series. A sample is treated as a spike when it jumps at least 20
  percentage points above both nearby samples, the nearby samples are within 8
  percentage points of each other, and both gaps are at most 20 minutes.
- Filtered tank samples keep `level_percent_raw` for diagnostics and expose
  `level_percent=null`, so charts bridge the bad point without deleting raw
  measurements.

## Session Lifecycle

Statuses currently used:

- `starting`: row inserted, open command is being confirmed.
- `running`: open command confirmed.
- `stopped`: manually stopped with successful close confirmation.
- `auto_stopped`: automatically stopped with successful close confirmation.
- `stop_failed`: physical result is uncertain (failed close or unconfirmed start).
- `start_failed`: historical failed start, or interrupted/unconfirmed start
  whose motorized valve was subsequently confirmed closed during recovery.
- `failed_no_watering`: controller accepted/start session exists, but physical
  telemetry indicates no watering after the grace period.

Manual start flow:

1. Clamp requested `duration_minutes` to `1..IRRIGATION_MANUAL_MAX_MINUTES`.
2. Initialize recovery before admission. Reject with HTTP `409` if a `running`,
   `starting` or `stop_failed` session exists, or recovery has not cleared its
   local interlock. DB failure cannot permit a new start.
3. Atomically recheck active sessions and insert `hc.irrigation_manual_session`
   with status `starting`. A concurrent loser returns HTTP `409` without OPEN.
4. After the reservation transaction commits, publish open and confirm valve
   state. DB exceptions or an unknown commit result do not authorize OPEN.
5. On confirmation, update session to `running`, store confirmation details, and
   invalidate `irrigation`.
6. On failure, keep uncertainty as `stop_failed`, store the failed start and
   recovery origin, and return HTTP `502`. Recovery may close it later; it must
   not reopen it. A late result cannot overwrite a session already reconciled;
   losing the conditional `starting → running` update returns HTTP `409`.

Manual stop flow:

1. If no `session_id` is provided, use the latest non-`physical_manual` session
   with `running`, `starting` or `stop_failed` status.
2. Return HTTP `404` if no running session exists.
3. Publish close command with reason `manual_stop`.
4. On confirmation, status becomes `stopped`.
5. On failure, status becomes `stop_failed`.
6. Invalidate `irrigation`.

Safety worker behavior:

- A single `irrigation-safety` worker performs stop supervision separately
  from the single serial `scheduler` worker that can wait for opening.
- Each safety callback has its own exception boundary. V2 effective-stop
  checks run first to preserve their stop policy/reason, then generic overdue
  sessions, then no-water detection. An exception in one does not skip the rest.
- `stop_overdue_sessions()` closes sessions whose `requested_stop_at` or
  `safety_stop_at` has passed.
- `fail_sessions_without_physical_watering()` marks old running sessions as
  `failed_no_watering` when both motorized and manual valves are reported
  closed.

Before these callbacks, the safety pass runs session recovery with its own
exception boundary. Recovery never issues OPEN. It is independent of the V2
domain flag, schedule weekday/date and seasonal start permissions.

## Session Recovery (HC-03)

On first service use after process start, persisted non-`physical_manual`
`starting` rows are classified as uncertain `stop_failed` rows before new HC
starts can pass. Existing retry counts are retained. The periodic pass also
classifies a `starting` row when its configurable grace expires or its requested
or safety stop deadline has passed. Young starts retain their existing window;
no automatic `starting → running` recovery or OPEN replay exists.

The existing `stop_payload.recovery` JSON stores origin status, reserved attempt
count, last/next attempt time, state and last message. No new schema or runtime
DDL is required. A conditional row UPDATE commits a slot and the next eligible
DB time before MQTT. At most one physical recovery attempt runs in a safety
pass, and that attempt allows exactly one CLOSE publish. The default budget is
three additional recovery slots; a crash before publish still spends its slot.
Normal/manual close attempts use their existing limits and do not reset this
automatic budget. This recovery claim is separate from HC-04 start admission.

Close success still needs HC-01's fresh, non-retained current-connection Nano
sample. A later fresh CLOSED observed after this recovery instance began
tracking the session may settle uncertainty without another command, including
during backoff or after budget exhaustion. Cached/retained/disconnected CLOSED
cannot. A failed or lost DB result commit leaves uncertainty and the spent
budget intact; a subsequent pass can reconcile it. Concurrent recovery claims
compare the previous recovery JSON and DB deadline, and cannot spend the same
slot twice.

Recovered failed closes become `auto_stopped`. Interrupted starts become
`start_failed` with a confirmed close in `stop_payload`, rather than being
reported as successful watering. Conditional final writes cannot overwrite an
explicit stop or newer recovery result. `physical_manual` records are excluded
from recovery classification, claims, final writes and status display.

After exhaustion the row stays `stop_failed`, blocks starts and requires
operator attention. It can still settle on fresh CLOSED or an explicit manual
close; the automatic budget never silently renews on restart. No historical
terminal `start_failed` records are blindly reclassified. With the safety
worker disabled, initial admission still scans/classifies persisted starts,
but automatic recovery needs the worker; manual close remains available.

The `session_recovery` read payload lists all unresolved sessions, including
ones outside the ten-row recent history: ID, status, age, reserved count,
next eligible time and attention/error. The irrigation page displays these
values and session error details. Read payload construction does not execute
recovery. The local interlock may conservatively remain set until the next
successful safety scan after the last row is resolved.

The initial stop-check pass precedes scheduler work. Both workers use
`IRRIGATION_SCHEDULER_POLL_SECONDS` (default 5 seconds, minimum 1), sleeping
after their respective passes; opening waits do not delay the safety worker.
The check interval also includes that worker's own DB/confirmation work.
This is not a hard physical-close deadline when DB, transport or a prior stop
is blocked. Solar-pump scheduling remains in its existing mixed start/stop
tick on the scheduler worker.

Process-local valve command ordering (HC-02):

- A close or raw manual `valve_stop` immediately invalidates pending OPEN
  confirmations/retries before waiting for any in-flight publication.
- Manual and V2 starts capture this generation before DB preparation, so a
  request already being prepared when stop arrives cannot publish afterwards.
  A request admitted during a pending stop also remains invalid after it ends.
- OPEN/CLOSE publication calls are ordered by a shared publication-only lock;
  opening reaction/ready waits hold no publication lock.
- A pending close blocks new OPEN publications until its confirmation ends.
  Concurrent close operations are serialized for this one physical valve.
- The old OPEN returns failed confirmation with `blocked_by=stop_request`
  after its current wait/observation returns; it cannot retry or accept a
  late OPEN result after cancellation. Existing 5/30-second waits, retry
  counts and fresh physical confirmation requirements are retained.
- The in-flight publication itself is not preempted. A stuck transport call
  can still delay the following CLOSE; DB/transport timeouts and physical
  failsafe behavior require their separate checks.

This command ordering is confined to one service/process. HC-04 supplies the
separate DB admission below; neither makes DB/physical completion atomic.
HC-03 adds the uncertain-session lifecycle while retaining publication order.

## Atomic Start Admission (HC-04)

`IrrigationSessionAdmission.reserve()` is shared by manual, V2 scheduled and
retained legacy start methods. It uses a fresh connection and one short
READ COMMITTED transaction: acquire a SHARE ROW EXCLUSIVE lock on the session
table, recheck `starting`/`running`/`stop_failed`, and insert a `starting` row.
Reads remain available; session writers are serialized during this transaction.
The recheck gets a new snapshot after the lock wait, including a physical
manual observation committed while admission waited.

For scheduled starts, eligibility (active/day/window/not started today) is
rechecked and `last_started_on` updated in the same transaction as insertion.
The caller's preliminary SELECT and rule evaluation are preparation only.
A losing reservation sends no OPEN, consumes no schedule day and reports no
confirmed execution. Even after the first session closes, an already-prepared
request cannot start the same schedule again on that DB-local date. The pilot
skip/audit path is unchanged and remains outside this reservation transaction.

The transaction commits before MQTT, confirmation waits or audit writes.
Local PostgreSQL lock/statement timeouts are 2/5 seconds, scoped to admission;
errors fail closed and roll back both the session and schedule day. If the
commit happened but its response was lost, no OPEN is authorized. The retained
`starting` row blocks further admission and HC-03 can reconcile it using CLOSE.
A missing admission dependency also fails closed. No runtime DDL or migration
is required, and pre-existing duplicates are preserved while blocking starts.

Active `physical_manual` observations still block HC admission, but they are
never created/reclassified by this gate. Ingest can record physical activity
alongside an HC session; this is not a second HC command owner. A manual API
request cannot claim the reserved `physical_manual` origin. The ingest tracking
logic and recovery exclusions are unchanged.

This is a cooperative application transaction, not a database uniqueness
constraint for arbitrary SQL writers. All HC insert paths use it; mixed old/new
controllers and uncoordinated SQL writes are not supported. Keep one active
backend: HC-02 command ordering, HC-03 startup recovery and scheduler workers
are not distributed ownership mechanisms. HC-08 audit-chain recovery, HC-20
legacy removal and HC-13 full I/O/worker deadlines remain separate work.

## Valve Confirmation

Live valve state is read directly from the MQTT monitor snapshot, using:

- `pump_metrics`
- `esp_nano_status`

Firmware timing supplied and verified by the operator on 2026-10-22: Nano
STATUS every 30 seconds, TELE every 10 seconds when enabled by Nano
configuration, UART offline timeout 40 seconds, and 250 ms TX silence after
a Nano command. Events and commands can also produce messages. ESP MQTT
publication is event driven and can repeat an older Nano sample.

Freshness and command waits are independent:

- TELE sample age is `pump_metrics.last_tele_sec_ago` plus elapsed time since
  MQTT receipt; its initial configurable limit is 25 seconds.
- STATUS sample age is `nano_status.last_status_sec_ago` plus elapsed time
  since MQTT receipt; its initial configurable limit is 70 seconds.
- Elapsed time uses a monotonic clock. MQTT wall-clock `timestamp` remains
  receipt metadata, not device sampling time. Repeating an old Nano sample
  with a new MQTT timestamp does not reset its sample age.
- Missing TELE is reported as unavailable (`tele_fresh=null`), and does not
  prevent use of valid STATUS feedback. Missing/invalid source-age fields
  cannot establish freshness.
- Nano liveness comes only from `nano_status.online`, independently of the
  two sample-age checks. A non-retained flag received on the current monitor
  connection is trusted for at most 40 seconds by default. An old `true`
  becomes unknown. `pump_metrics` and diagnostic flags cannot establish
  liveness. A fresh STATUS sample may coexist with unknown/offline Nano
  liveness; a fresh online flag may coexist with an old STATUS sample.
- Confirmation requires the monitor connected, Nano online, a non-retained
  sample from the current monitor connection, and an acceptable source age.
  It must prove sampling after the start of the current publish attempt.
  Since `*_sec_ago` counters have second resolution, proof uses
  `received_monotonic - source_age - 1 second > command_started_monotonic`.
  An immediate age-zero republication alone is insufficient; later fresh
  feedback can confirm within the existing wait. A retry gets a new boundary.
- The freshest eligible Nano sample wins per field, rather than a fixed
  preference for `pump_metrics`. Confirmation details preserve topic,
  receipt/source age, connection generation, and rejection reason.

Open confirmation:

- success if motorized valve is exactly `OPEN`;
- reaction is considered seen for `OPEN`, `OPENING`, `BETWEEN`, `MOVING_OPEN`,
  or eligible current above `0.01 A`;
- each attempt publishes the command, waits the configured reaction/ready
  delays, and records observed states.

Close confirmation:

- success if motorized valve is exactly `CLOSED`;
- reaction is considered seen if valve text indicates closed/closing or current
  is above `0.01 A`;
- each attempt publishes the command, waits the configured reaction/closed
  delays, and records observed states.

The initial 25/70/40-second freshness limits must be reviewed against measured
live delays. They do not change the existing 5/30-second reaction/final waits
or retry counts. Missing/stale feedback returns failed confirmation through
the existing API/session status handling; close publication remains available
while disconnected or Nano liveness is unknown. No-water session failure also
requires fresh samples of both valves acquired after that session started.

Manual valve guard:

- Reads latest `manual_valve_state` from the ESP irrigation entity.
- Blocks scheduled starts when state contains `OPEN`, `OPENING`, `BETWEEN`, or
  `MOVING`.
- Does not block when state contains `CLOSED`.

## Schedule Rules

`hc.irrigation_schedule` can have multiple rows per weekday, so one day can
contain several independent watering windows, for example evening and dawn:

- `day_of_week` is `0..6`.
- The code maps current day using `extract(isodow from now())::int - 1`, so
  Monday is `0` and Sunday is `6`.
- `start_time` must be before `stop_time`.
- Active schedules are eligible only on their configured day.
- A schedule starts only when local time is within `[start_time, stop_time)`.
- `last_started_on` prevents repeated starts on the same date per schedule row.
- `last_stopped_on` prevents repeated stop handling on the same date per
  schedule row.
- Updating today's active schedule resets `last_started_on` and
  `last_stopped_on` when start/stop/active values changed.
- The UI keeps at least one row per weekday; extra windows can be added and
  deleted.

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
  includes `irrigation` in `publish_domains`; it runs due starts and the
  existing solar-pump tick on the scheduler worker.
- `scheduler_stop_tick()` applies the same V2 domain gate and runs only
  `stop_v2_due_schedules()` on the safety worker. Generic overdue-session
  supervision remains available independently of the V2 domain gate.
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
