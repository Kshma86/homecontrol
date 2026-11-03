# Xiaomi X10 Scenarios And Eval Cases

## Unknown Command

Given:

- `/api/xiaomi-x10/command` receives an unsupported command.

Expected:

- The service raises/returns an unknown command error.
- No MQTT publish happens.
- `robot` context is not invalidated by a failed command.

## Direct Command

Given:

- Command is `start`.

Expected:

- Publish payload to `homecontrol/xiaomi_x10/command/start`.
- Invalidate `robot`.
- Response includes `context.read_after` for `/api/context/robot`.

## Missing MQTT Telemetry

Given:

- MQTT state does not contain robot state, battery, charge, task, mode, suction,
  or water level.
- A capture status file contains valid telemetry.

Expected:

- `telemetry_source` is `capture`.
- `last_known_telemetry` identifies the capture file and event.
- Dashboard state is populated from capture data.

## Map URL Sanitization

Given:

- Current map PNG is a path-like value.

Expected:

- The API exposes `/api/xiaomi-x10/maps/<filename>`.
- Directory components are stripped.

## V2 Weekly Schedule Already Matches

Given:

- Desired HC-owned schedule rows match robot scheduler entries.

Expected:

- No publish is attempted.
- V2 executions are marked confirmed with reason
  `robot_schedule_already_matches`.

## V2 Weekly Schedule Invalid

Given:

- A desired HC-owned schedule row has no segments or missing map/time/mode.

Expected:

- Publish is blocked.
- Execution status becomes `blocked`.
- Result reason is `invalid_x10_schedule_payload`.

## V2 Robot Active

Given:

- Robot state text indicates cleaning, room cleaning, active, or scheduled.

Expected:

- Weekly schedule publish is blocked.
- Result reason is `x10_active_cleaning`.

## Suggested Tests

- Unknown commands do not publish.
- Capture fallback is used only when MQTT telemetry is missing.
- Schedule validation rejects empty segments.
- Active cleaning blocks weekly schedule publish.
- Matching desired schedule avoids unnecessary publish.
