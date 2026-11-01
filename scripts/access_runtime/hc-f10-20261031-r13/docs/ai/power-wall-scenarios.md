# Power Wall Scenarios And Eval Cases

## Boolean Parsing

Given:

- Request values include `true`, `false`, `on`, `off`, `1`, `0`, `yes`, `no`.

Expected:

- They map to booleans.
- Unknown values return validation errors for policy/scheduler endpoints.

## Always-On Policy

Given:

- `always_on` is set true for an entity.

Expected:

- Policy is upserted.
- Scheduler is disabled for that entity.
- `power_wall_state` cache is invalidated.

## Always-On Guard

Given:

- Entity is online.
- `always_on = true`.
- Latest switch state is false.
- Last guard action is older than repeat window.

Expected:

- Publish ON.
- Update policy `last_action_at`, `last_action`, and `last_error`.

## Scheduler Plan

Given:

- Scheduler is enabled.
- Entity is online.
- Current time is inside scheduler window.
- Switch is off.
- No planned/running session exists.

Expected:

- Insert a `planned` session with randomized future start.
- Do not publish immediately.

## Scheduler Start

Given:

- A planned session has `planned_start_at <= now()`.

Expected:

- Publish ON.
- Mark session `running` on success or `failed` on publish failure.
- Set `planned_end_at` based on randomized on-duration.

## Scheduler Stop

Given:

- A running session has `planned_end_at <= now()`.

Expected:

- Publish OFF.
- Mark session `completed` on success or `failed` on publish failure.

## Outside Window

Given:

- Current time is outside scheduler window.
- Switch is on.

Expected:

- Publish OFF.
- Running session becomes `completed` on success or `failed` on failure.
- Planned sessions are cancelled with error `outside scheduler window`.

## Climate Auto Sync

Given:

- Climate command turns power on.
- Power-wall policy has `auto_climate = true`.

Expected:

- Matching smart plugs are turned ON.
- Policy last action records `climate_auto_on`.

## HC Server Plug Identity

Given:

- User asks about `HC szerver` consumption.

Expected:

- Resolve the question to the Tuya smart plug / consumption meter named
  `HC szerver`.
- Use `server_power` summary if available.
- If only `power_wall.devices` is available, answer with instantaneous
  `power_w` and state that historical averages are unavailable.
- Do not answer from irrigation pump runtime or AI server status.

## Suggested Tests

- Scheduler/always-on mutual exclusion.
- Overnight window calculation.
- Publish failure does not mark session completed.
- Tuya and Zigbee command payloads are correct.
- Display-name duplicate suffix behavior.
