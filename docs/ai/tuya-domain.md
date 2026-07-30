# Tuya Domain Context

## Scope

The Tuya module reads Tuya device state and publishes switch commands through
the Tuya poller/command bridge.

Primary implementation:

- `infra/backend/energy_device_service.py`
- `infra/backend/power_wall_service.py`
- `apps/tuya-poller/tuya_poller.py`
- `infra/db/010_tuya_poller.sql`

## Ownership

- Durable truth: `hc.device`, `hc.entity`, `hc.entity_state`,
  `hc.measurement`, `hc.entity_presence`.
- Read-model owner: `EnergyDeviceService.tuya_state_payload()`.
- Command owner: `PowerWallService.tuya_switch_command()`.
- Context section: `tuya`.
- Related context: `power_wall`.

## API Endpoints

Read endpoints:

- `GET /api/context/tuya`
- `GET /api/tuya/state`

Mutation endpoint:

- `POST /api/tuya/command`

## State Payload

`tuya_state_payload()` returns:

- `devices`: active Tuya entities with current state map.
- `state_rows`: raw state rows.
- `recent_measurements`: six-hour measurement aggregates.
- `summary`: total, online, degraded, offline, unknown counts.

Cache:

- `tuya_state` for about 8 seconds.

## Command Payload

Switch command topic:

```text
homecontrol/cmd/tuya/{entity_name}/switch
```

Payload:

```json
{
  "value": true,
  "entity_id": 123,
  "entity_name": "Name",
  "source": "homecontrol-tuya-tab",
  "ts": 1234567890
}
```

Command lookup may use `entity_id` or `entity_name`.

## Safety Rules

- Only active Tuya devices/entities can be commanded.
- A command affects both `tuya` and `power_wall` contexts.
- Clear both `tuya_state` and `power_wall_state` caches after a Tuya switch
  command.
- Do not assume every Tuya device is a switch; check metrics/state.
