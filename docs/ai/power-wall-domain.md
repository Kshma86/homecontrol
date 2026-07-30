# Power Wall Domain Context

## Scope

The power wall module manages smart plugs, power telemetry, battery-powered
Zigbee devices, always-on protection, climate auto-sync, and randomized plug
scheduling.

Important naming rule:

- `HC szerver` is a smart plug / consumption-meter entity for the physical
  HomeControl server.
- It is selected by display name `HC szerver`, known Tuya external id
  `bf6ac883a687a6a2a2ci8l`, or entity name `hc szerver`.
- Do not confuse it with the AI server service, Ollama, or remote AI node.

Primary implementation:

- `infra/backend/power_wall_service.py`
- `infra/backend/energy_device_service.py`
- `infra/backend/api_route_modules.py`
- `infra/db/011_power_wall_zigbee_switch.sql`
- `infra/db/012_power_wall_always_on.sql`
- `infra/db/013_zigbee_power_wall_plugs.sql`
- `infra/db/017_power_wall_scheduler.sql`
- `infra/db/021_power_wall_display_names.sql`
- `infra/backend/tests/test_power_wall_service.py`

## Ownership

- Durable truth: `hc.power_wall_policy`, `hc.power_wall_schedule_session`,
  entity state/measurements.
- Command owner: `PowerWallService`.
- Context section: `power_wall`.
- Related context: `tuya`, `climate`, `performance`.

## Supported Device Platforms

Commandable entities must be active and on one of:

- `zigbee`
- `tuya`

Zigbee command:

```text
{topic_base}/set
```

Payload:

```json
{"state": "ON"}
```

Tuya command:

```text
homecontrol/cmd/tuya/{entity_name}/switch
```

Payload:

```json
{
  "value": true,
  "entity_id": 123,
  "entity_name": "Plug",
  "source": "homecontrol-power-wall",
  "ts": 1234567890
}
```

## API Endpoints

Read endpoints:

- `GET /api/context/power_wall`
- `GET /api/power-wall/state`
- `GET /api/power-wall/history?entity_id=...`
- `GET /api/power-wall/scheduler/sessions?entity_id=...`

Mutation endpoints:

- `POST /api/power-wall/policy`
- `PUT /api/power-wall/display-name`
- `PUT /api/power-wall/scheduler`
- `POST /api/power-wall/command`

Tuya tab command endpoint also affects power wall:

- `POST /api/tuya/command`

## Policy Fields

`hc.power_wall_policy` contains:

- `always_on`
- `auto_climate`
- `display_name`
- `scheduler_enabled`
- `scheduler_window_start`
- `scheduler_window_end`
- `scheduler_min_on_minutes`
- `scheduler_max_on_minutes`
- `scheduler_min_off_minutes`
- `scheduler_max_off_minutes`
- `scheduler_jitter_minutes`
- `last_action_at`
- `last_action`
- `last_error`

Rules:

- Enabling `always_on` disables scheduler for that entity.
- Enabling scheduler sets `always_on` false.
- `display_name` is optional and capped at 80 characters.
- Duplicate display names get a suffix from location, platform, or external id.

## Always-On Guard

`guard_tick()`:

- selects active online Zigbee/Tuya entities with `always_on = true`;
- acts only when `switch_state` is false;
- respects `POWER_WALL_GUARD_REPEAT_SECONDS`;
- publishes ON;
- records last action and error in policy.

Safety rule:

- Do not repeatedly spam ON commands; keep the repeat window.

## Scheduler

`scheduler_tick()`:

- only considers entities where `scheduler_enabled = true` and `always_on` is
  false;
- skips offline/unknown devices for start actions;
- supports windows that cross midnight;
- creates a `planned` session when the switch is off and inside the window;
- after planned delay, turns switch on and marks session `running`;
- after planned duration, turns switch off and marks `completed` or `failed`;
- outside the window, turns off running switches and cancels planned/running
  sessions as needed.

Window behavior:

- equal start/end means always inside the window;
- normal windows use `start <= now < end`;
- overnight windows use `now >= start OR now < end`.

Random duration rules:

- on/off durations are random within configured min/max;
- jitter can add or subtract minutes;
- final duration is clamped to at least 1 minute;
- if max is below min, max is treated as min.

## Climate Auto Sync

`sync_auto_climate(power)`:

- accepts only `on` or `off`;
- targets policies with `auto_climate = true`;
- publishes matching switch value;
- records `last_action` as `climate_auto_on` or `climate_auto_off`.

## State Payload

`state_payload()` returns:

- `devices`: commandable power devices with policy and state.
- `battery_devices`: Zigbee battery-only devices.
- `state_rows`: raw state rows for power devices.
- `recent_measurements`: six-hour measurement aggregates.
- `summary`: totals by platform/status and battery counts.

Cache:

- `power_wall_state` for about 8 seconds.
- History payloads are cached by entity for about 30 seconds.

## Safety Rules

- Do not command inactive devices or unsupported platforms.
- Do not command a Zigbee entity without `topic_base`.
- Do not let scheduler and always-on fight each other.
- Do not mark scheduler sessions completed when publish failed.
- When a command changes power-wall state or policy, invalidate
  `power_wall`.
