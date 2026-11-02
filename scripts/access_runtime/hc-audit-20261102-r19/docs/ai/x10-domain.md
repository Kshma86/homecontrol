# Xiaomi X10 Robot Domain Context

## Scope

The X10 module observes and commands a Xiaomi X10 robot vacuum through an MQTT
bridge. It also stores map, room, and schedule metadata.

Primary implementation:

- `infra/backend/robot_service.py`
- `infra/backend/scheduler_service.py`
- `apps/xiaomi-x10/`
- `infra/db/002_xiaomi_x10.sql`
- `infra/db/006_v2_x10_plan_execution_shadow_backfill.sql`
- `infra/db/008_v2_x10_executor_mode.sql`
- `infra/backend/tests/test_robot_service.py`
- `infra/backend/tests/test_scheduler_service.py`

## Ownership

- Durable truth: `hc.x10_map`, `hc.x10_room`, `hc.x10_schedule`,
  `hc.x10_schedule_day`, entity state/measurements.
- Live truth: MQTT monitor values under the X10 base topic.
- Command owner: `RobotService.command()` for direct UI/API commands.
- Scheduler owner: `SchedulerService` for V2 audit and weekly schedule publish.
- Context section: `robot`.

## MQTT

Default entity topic base:

```text
homecontrol/xiaomi_x10
```

Commands publish to:

```text
homecontrol/xiaomi_x10/command/<command>
```

Allowed commands:

- `status`
- `refresh_map`
- `check_map`
- `select_map`
- `read_scheduler`
- `start`
- `stop`
- `home`
- `room_clean`
- `schedule_clean`
- `schedule_clean_week`
- `capture_start`
- `capture_stop`
- `set_clean_mode`
- `set_suction`
- `set_water_level`

Unknown commands raise `ValueError("unknown command")`.

## API Endpoints

Read endpoints:

- `GET /api/context/robot`
- `GET /api/xiaomi-x10/state`
- `GET /api/xiaomi-x10/rooms`
- `GET /api/xiaomi-x10/map`
- `GET /api/xiaomi-x10/cache`
- `GET /api/xiaomi-x10/maps/<filename>`

Mutation endpoint:

- `POST /api/xiaomi-x10/command`

## State Payload

`RobotService.state_payload()` returns:

- MQTT connection summary.
- Bridge status and last seen.
- Telemetry availability and missing fields.
- Robot state, state text, battery, charge status, task state.
- Clean mode, mop attached, suction, water level.
- Current map, map image URL, rooms, map object, MD5.
- Robot and dock positions.
- Room-clean status.
- Capture status.
- Scheduler entries from the bridge.
- Catalog from database maps/rooms.
- Latest command result and errors.
- Raw topics.

If live MQTT state is missing key telemetry, the service falls back to the most
recent capture status in `x10_maps/captures/*.jsonl`.

## Database Objects

Important tables:

- `hc.x10_map`
- `hc.x10_room`
- `hc.x10_schedule`
- `hc.x10_schedule_day`

HC day index:

- `0..6`
- Keep consistent with existing scheduler code and X10 day-mask conversion.

Seeded maps include:

- `3`: `Földszint`
- `197`: `1. Szint`
- `44`: `2. Szint`

## V2 Scheduler Rules

V2 X10 audit creates event/plan/execution records with no side effects in
shadow mode.

V2 weekly schedule execution:

- Runs only when the scheduler engine includes `xiaomi_x10` in
  `publish_domains`.
- Reads HC-owned rows from `hc.x10_schedule_day`.
- Builds desired weekly schedules.
- Validates required fields: `day_index`, `map_id`, `start_time`, `mode`,
  `suction`, `water_level`, and non-empty `segments`.
- Compares desired rows to robot scheduler entries.
- If already matching, marks executions confirmed without publishing.
- Blocks publishing when robot appears active or scheduled.
- Publishes one weekly schedule payload to the X10 weekly schedule topic when
  differences exist and preconditions pass.

## Safety Rules

- Do not rewrite robot weekly schedules while the robot appears active.
- Do not publish invalid schedules with missing map, room segments, mode,
  suction, or water level.
- Do not treat shadow/audit plan rows as real publishes.
- Do not infer rooms from labels only; use `hc.x10_room` or bridge-provided room
  metadata.

## Context Invalidation

Direct robot commands invalidate `robot` and return a `context.read_after`
hint.

Scheduler-side X10 changes should invalidate `scheduler`, `scheduler_ai`, and
`robot` only when the observable robot state or schedule cache changes.
