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

- `power`: `on` or `off`; schedule rows may also use `keep`
- `mode`: `auto`, `cool`, `dry`, `fan`, `heat`; schedule rows may also use
  `keep`
- `target_temperature`: integer `8..30`
- `fan_speed`: `auto`, `low`, `mediumlow`, `medium`, `mediumhigh`, `high`,
  `quiet`, `turbo`; schedule rows may also use `keep`
- Extra switches exposed in live state/commands when supported by the bridge:
  `quiet`, `turbo`, `sleep`, `xfan`, `power_save`
- `light`: `on` or `off`
- `buzzer`: `on` or `off`; persisted in the bridge volume and applied to future
  HC commands, including schedules. Changing this alone sends no AC control
  packet. Live state reports the configured preference, not hardware readback.
- `extra_fan`: schedule-only `keep`, `on`, or `off` for the configured
  `climate_extra_fan_socket` binding
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

- The bridge loads a persistent `buzzer` preference (default `off`) on each
  connection. With `off`, HC commands include `Buzzer_ON_OFF=1` to suppress command beeps on supported
  firmware (including reported support for v1.31). This does not verify the
  audible result or guarantee silence for commands from other controllers.
- Invalid command values raise `ValueError`.
- Empty command body becomes a refresh command.
- Successful `power` on/off commands may trigger power-wall auto sync.
- Every queued command invalidates `climate` and `power_wall`.
- The extra fan socket policy supports `auto_climate_delay_minutes` (integer
  0..120, default 0). The climate-page input saves through `/api/power-wall/policy`.
  Automatic ON queues a durable `auto_climate_on_at`; repeated ON while pending
  keeps the existing deadline. The power-wall loop executes due starts (normally
  within 10 seconds of the deadline). Automatic OFF and manual socket commands
  cancel pending starts; disabling Auto also cancels them. OFF is immediate.
  Delay changes apply to the next start, leaving an existing deadline unchanged.
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

## Combustion command delivery (HC-05)

The supplementary combustion guard separates command attempts, publisher
success and later device observations. Extractor OFF and indicator commands
use at most `COMBUSTION_COMMAND_MAX_ATTEMPTS` attempts (default 3), spaced by
`COMBUSTION_COMMAND_RETRY_SECONDS` (default 10) on a monotonic clock. A publisher
failure/exception does not set `shutdown_sent` or change `indicator_on`.
An accepted publish alone does not end automatic retries while observation
is missing and the existing enabled/auto-shutdown/current-danger policy still
requires OFF. A latch alone does not change that policy. The extractor stop is attempted before indicator/event work,
and each actuation has its own failure boundary.

`actuation.shutdown` and `actuation.indicator` expose desired command, target,
attempt count, publisher result, observation timestamp, next retry and
`requires_attention` on exhaustion. The existing flags describe accepted
commands (or matching indicator observations), not physical acknowledgements.
Exhaustion stays visible without restarting the budget on every tick or level
change. A new target/desired command starts a new episode; a freshly observed
fan restart after observed OFF also starts a new stop episode.

Observations require non-retained entity-state metadata, a timestamp strictly
after the first attempt, and age within
`COMBUSTION_OBSERVATION_MAX_AGE_SECONDS` (initial default 60). Extractor low
numeric power (`power` or `power_w` at/below `fan_off_w`) is the stop observation.
Indicator ON requires switch state, brightness and xy colour (tolerance 0.01);
OFF requires switch state alone. Explicitly offline indicator radio cannot
confirm. Missing/stale/future/unknown-retain data cannot end retries.

These timestamps are ingest/DB observations, not device sample timestamps or
command IDs: source freshness/physical correlation and generic MQTT transport
semantics remain HC-09 work. The observation flag records past matching
evidence; it is not a permanent online guarantee. Retry limits are initial
configuration values requiring supervised operational measurements.

Pulsed lights retain their pulse deadline even if ON transport fails; cleanup
OFF has its own bounded episode. A failed OFF does not claim the light is off.
Further pulses wait for observed OFF, so missing feedback can suspend pulses
and require operator attention. Explicit preview keeps its existing finite
pattern and only updates the light flag after successful publish; it does not
prove observation. Continuous red takes precedence over a pulse cleanup.

HC-06 feedback follow-up (r3, 2026-10-25): ingest refreshes the bound
extractor's `power/power_w` and indicator's `switch_state/brightness/color`
current state from every validated non-retained device message, including
unchanged values. History still uses its configured deadband/interval cache;
state-only refreshes do not advance that cache. Binding lookup follows the
existing 60-second rules cache. Disabled rules and history-only storage stay
effective. Retained feedback cannot replace a live observation. Zigbee
`/set` and `/get` requests, including property subtopics, are ignored before
presence/state processing. CO/smoke event handling, 300-second continuous-input
expiry and bounded actuation retries are unchanged. An exhausted OFF episode
can settle from a later real OFF observation without resetting its budget.

The delivery retry episodes remain process-local. HC-06 below adds durable
latch/CO history and a read-only decision snapshot. Keep one active backend;
HC-13 full I/O/worker deadlines and physical stop latency remain separate.
The existing physical alarms remain independent.

## Combustion Decision Ownership And Durable Latch (HC-06)

Only the single combustion worker `tick()` advances fan debounce, CO trend,
warning and automatic latching. Overlapping ticks do not start another decision.
`evaluate()` is a compatibility read adapter; it no longer runs the decision.
`GET /api/combustion-safety/state` and `last_snapshot` return independent copies
of the last complete snapshot, with no DB reads/writes, publish or evaluation.
Events are read by the worker. A short snapshot lock allows GET to complete even
while a decision/publish is blocked; the worker publishes its complete decision
before actuation/log I/O and then updates delivery results.

The payload includes `evaluated_at_epoch`, `evaluation_age_seconds`, `stale`,
`input_health`, `persistence` and `evaluation_error`. Age uses a monotonic clock.
`COMBUSTION_SNAPSHOT_MAX_AGE_SECONDS=5` initially defines stale worker output;
missing/stale output is never shown as healthy. Known latch evidence remains
visible, and unknown fan state cannot grant the climate-window exemption.
The UI shows an unknown state or retained latch, and admin shows evaluation age
and whether restoration is known. GET does not refresh the evaluation timestamp.

Input policy (hc-sleeping-20261023-r2, deployed 2026-10-23): the bound CO and smoke
devices are sleeping, event-driven sensors. A known last alarm/concentration
state remains valid until another event replaces it, provided radio presence
is confirmed. Silence is not a new clear event. The existing Zigbee radio
presence policy currently uses `lastSeen` with a six-hour limit; that limit is
separate from measurement age and was not changed by this follow-up.
`COMBUSTION_INPUT_MAX_AGE_SECONDS=300` still applies to continuous fan power and
air-opening feedback, not to sleeping CO/smoke states.

| Evidence | Decision / acknowledgement |
|---|---|
| Positive CO/smoke alarm or shutdown-level CO, including old positive evidence | Conservatively latch danger; never clear it because it became old. |
| Known last CO and configured smoke states, confirmed radio presence, no fault | May support normal levels even after months without a new event; existing latch still needs explicit ACK. |
| Missing, future, invalid, retained or unknown-retain clear event; offline/unknown radio; fault/unknown fault | No healthy/clear proof and no ACK. Radio presence never invents a missing clear state. |
| Fresh finite numeric fan power | Advance the existing on/off thresholds and delays using monotonic time. |
| Unknown fan power | Break the pending debounce interval; preserve the internal prior state, expose fan as unknown, and do not clear CO warning or grant the climate exemption. |
| Old/retained/offline open-contact report | Cannot prove a primary/secondary air-supply opening. |
| Smoke binding intentionally absent | Optional; bound smoke requires known state and confirmed radio presence. CO is required for ACK. |

Accepted sleeping-sensor events still require explicit `meta.retained=false`,
a finite non-future DB timestamp, and a valid value. The event timestamp is not
refreshed by a radio check, GET, restart or ACK. Continuous input additionally
requires an age within its configured limit. Samples arriving during DB reads
are checked against read time, not the earlier tick-start time. These are
ingest/DB timestamps; device sample age/correlation remains an HC-09 dependency.
Radio presence and continuous-input limits remain separate policies.
Every change of `smoke/smoke_alarm/fire/alarm`, CO alarm/fault and numeric
`carbon_monoxide_value/co/co_ppm` bypasses ingest min-interval/deadband throttling;
this includes both alarm and clear transitions and small threshold crossings.
Unchanged values may remain throttled. Retained reconnect replay cannot replace
known provenance for the same value or clear/decrease recorded alarm evidence.
Positive retained alarms/increases are still processed conservatively as
untrusted evidence. A same-valued live confirmation can replace prior retained
or unknown provenance without waiting for the history interval. The worker reads accepted state on its
normal tick; this is not a new end-to-end delivery deadline or durable event queue.
Disabled guard still observes/latches danger and reports `would_level`; disabling
or changing configuration never acknowledges a latch.

Migration `058_combustion_safety_runtime.sql` adds one singleton runtime row:
latch, sticky CO warning, last numeric CO/sample timestamp, revision, update/ACK
timestamps. No business configuration is rewritten and no runtime DDL is issued.
Apply the migration before deploying the backend. First installation starts
latched because no trustworthy prior runtime record exists; an explicit ACK
with known clear states and confirmed radio presence is required. Reapplying
the migration never resets an existing row.

The worker restores the row before deciding, preserves pending in-memory danger
across DB recovery, and commits changes before actuation/event logging. Updates
compare the expected revision, so an old result cannot silently overwrite newer
state. Successful committed latch/history survives process restart. Missing
schema/row or DB errors remain visible and cannot silently become clear. A latch
seen while the DB is unavailable is pending in memory until the next successful
commit: simultaneous process loss before that commit cannot be made durable by
this DB-only mechanism. Event-log failure does not erase the runtime latch.

`POST /api/combustion-safety/acknowledge` is the explicit exception to automatic
worker ownership. It is serialized with the worker, uses a fresh restored
snapshot and rechecks current bindings, thresholds and CO/smoke inputs through
read-only queries; it never advances debounce or CO history, and never publishes.
Active/newly arrived danger, uncertain inputs, changed bindings or stale worker
output returns conflict. A clear is reported only after the revision-checked DB
commit, and does not refresh the worker timestamp. Commit failure/uncertainty
keeps the local latch and exposes restoration uncertainty; the actual DB result
is reloaded on a later worker pass. In particular, a lost ACK reply may mean its
transaction committed despite the API failure; no false success is returned.

The locks and revision check are not distributed worker ownership. Keep one
active backend. HC-09 transport/source-age guarantees, HC-13 full I/O deadlines
and HC-07 existing unrelated bootstrap rewrites remain separate. No automatic
fan re-energization, opening-policy rebinding or climate-resume change was added.

## Window interlock

`climate_window_guard.py` intercepts HC climate MQTT commands, including V2
scheduler commands. Active opening sensors with `climate_relevant=true` block
new ON commands immediately. Unknown contact or explicitly offline radio also
blocks. While the combustion service reports `fan_active`, a known open sensor
with `extractor_air_role=primary` is exempt only from the climate interlock.
Combustion safety still sees the real contact state.

The one-second combustion worker also evaluates the climate interlock. Running
climate is stopped after `open_delay_seconds` (default 60). A durable desired
command resumes after all blockers clear for `close_delay_seconds` (default 60).
Later HC scheduler/manual changes update the desired settings; accepted OFF
cancels resumption. Power-wall auto fan follows actual stop/resume actions.
Countdowns restart conservatively after backend restart. Changes through a
physical remote are not durable HC intent.

`climate.window_guard` exposes blockers, extractor exceptions, suspended state,
and approximate remaining delay. `POST /api/climate/gree/window-guard` saves
integer `open_delay_seconds` / `close_delay_seconds` in range 0..3600.
The Climate tab shows status and allows saving both delays. The singleton table
is created lazily, also documented by migration 057. Schedule rows and season
selection are not changed by this feature.
