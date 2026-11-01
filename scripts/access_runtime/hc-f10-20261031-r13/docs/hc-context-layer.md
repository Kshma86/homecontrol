# HC Context Layer

## Goal

The HC Context Layer is a shared in-memory read model for HomeControl consumers:

- Web UI
- Mobile app
- AI assistant
- ML modules
- Future HC modules and RTK robotics

The context layer is not the source of truth. PostgreSQL remains the durable truth source. Existing domain logic and endpoints continue to work while consumers are migrated gradually.

## First Compatible Slice

The first implementation lives inside the backend process:

- `infra/backend/context_service.py`
- `GET /api/context`
- `GET /api/context/<section>`
- `GET /api/context/ai/summary`
- `POST /api/context/invalidate`

This is intentionally read-only except for memory-cache invalidation.

## Object Model

Top-level context:

- `house`: system health, active errors, warnings, peripheral/runtime summary
- `realtime`: fast-changing domain states
- `statistics`: slower aggregate states
- `events`: warnings, errors, open issues

Realtime sections:

- `weather`
- `irrigation`
- `climate`
- `robot`
- `power_wall`
- `solar`
- `notes`

Statistics sections:

- `performance`
- `home_statistics`
- `irrigation_statistics`
- `climate_power_history`

Expensive realtime sections use the statistics TTL even though they are emitted under `realtime`:

- `scheduler`
- `scheduler_ai`
- `irrigation_pilot`
- `climate_schedules`
- `performance`

## Cache Strategy

The context service is a read-through memory cache.

- Realtime TTL: `HC_CONTEXT_REALTIME_TTL`, default `5` seconds
- Statistics TTL: `HC_CONTEXT_STATISTICS_TTL`, default `60` seconds
- Force refresh: `?force=1`
- Invalidate one section: `POST /api/context/invalidate` with `{"section":"weather"}`
- Invalidate all sections: `POST /api/context/invalidate` with `{}`

## API Examples

Default lightweight context:

```http
GET /api/context
```

Full context:

```http
GET /api/context?full=1
```

Selected sections:

```http
GET /api/context?sections=weather,climate,robot
```

Single section:

```http
GET /api/context/weather
```

AI-ready summary:

```http
GET /api/context/ai/summary
```

## Migration Plan

1. Keep all existing API routes and background workers unchanged.
2. Add context sections as adapters over existing domain snapshot builders.
3. Switch AI chat payloads to include `/api/context/ai/summary` instead of allowing SQL-like access.
4. Move Web UI tabs one by one from old domain endpoints to `/api/context` sections.
5. Split route functions into pure payload builders where needed.
6. Add event-driven invalidation from MQTT/domain commands.
7. Move the context layer to a separate service only if backend-process memory cache becomes limiting.

## Current Boundaries

The Context Layer owns shared read models. Mutations still run through the existing domain-safe command endpoints, but those endpoints now report their context impact through a shared command layer.

Parameterized drilldown endpoints remain outside the global context read model by design:

- `GET /api/power-wall/history?entity_id=...`
- `GET /api/power-wall/scheduler/sessions?entity_id=...`
- `GET /api/backup/<name>/contents`
- `GET /api/backup/<name>/compare?path=...`
- `GET /api/xiaomi-x10/map`
- `GET /api/xiaomi-x10/maps/<filename>`

These endpoints answer scoped inspection questions rather than publishing whole-system state.

## Migration Status

- AI chat receives `GET /api/context/ai/summary` automatically through `/api/ai/chat`.
- Irrigation initial bootstrap and live UI refresh now read the `irrigation` section from the Context Layer.
- The legacy `GET /api/irrigation/state` endpoint remains available, but it now serves the same context-backed irrigation read model.
- Irrigation commands, manual start/stop, schedule updates, pilot config, and weather refresh still use their existing command endpoints. These endpoints now delegate to the irrigation domain service and invalidate the relevant context cache after changes.
- Robot/Xiaomi X10 UI reads now use `GET /api/context/robot`; the legacy `GET /api/xiaomi-x10/state` endpoint remains as a context-backed compatibility endpoint.
- Climate UI reads now use `GET /api/context/climate`; the legacy `GET /api/climate/gree/state` endpoint remains as a context-backed compatibility endpoint.
- Power wall UI reads now use `GET /api/context/power_wall`; command and policy endpoints invalidate the `power_wall` context section.
- Solar UI reads now use `GET /api/context/solar`; the legacy `GET /api/solar/state` endpoint remains as a context-backed compatibility endpoint.
- Performance UI reads now use `GET /api/context/performance`; the legacy `GET /api/performance` endpoint remains as a context-backed compatibility endpoint.
- Notes UI reads now use `GET /api/context/notes`; note create/update/delete endpoints still return the legacy wrapper shape and invalidate the `notes` context section.
- Tuya UI reads now use `GET /api/context/tuya`; Tuya commands invalidate both `tuya` and `power_wall` context sections.
- Scheduler UI reads now use `GET /api/context/scheduler`; scheduler config updates invalidate the `scheduler` context section.
- Backup UI reads now use `GET /api/context/backup`; backup settings, create, and restore invalidate the `backup` context section.
- Irrigation pilot reads now use `GET /api/context/irrigation_pilot`; pilot config, evaluation, and weather refresh invalidate the `irrigation_pilot` context section.
- Irrigation statistics reads now use `GET /api/context/irrigation_statistics`.
- Home environment statistics reads now use `GET /api/context/home_statistics`.
- Climate history and schedule reads now use `GET /api/context/climate_power_history` and `GET /api/context/climate_schedules`; climate schedule mutations invalidate the schedule context.

## Refactor Status

- `infra/backend/command_service.py` is now the central command/context-impact layer. Existing command endpoints still perform the same domain work, but invalidation and `context.read_after` metadata are routed through this shared service.
- The frontend `api()` wrapper now observes command responses with `context.read_after`, refreshes those context endpoints in the background, and notifies subscribed UI modules.
- MQTT monitor updates now trigger targeted context invalidation for irrigation, robot, climate, and Tuya/power-wall sections.
- Backup domain logic has been extracted from `app.py` into `infra/backend/backup_service.py`. Flask now keeps only thin route wrappers and context payload wiring for backup reads and mutations.
- Performance and system status collection has been extracted into `infra/backend/system_status_service.py`, including Docker socket access, container stats, PostgreSQL connection stats, worker status, and the performance context snapshot.
- AI node management has been extracted into `infra/backend/ai_node_service.py`, including node health probes, Wake-on-LAN, SSH command orchestration, and delayed power-off scheduling.
- Power wall domain logic has been extracted into `infra/backend/power_wall_service.py`. It now owns switch command payloads, Tuya command lookup, always-on guard behavior, climate auto-sync, scheduler planning/ticking, policy mutations, scheduler drilldowns, and the `power_wall` context read model.
- Irrigation domain logic has moved into `infra/backend/irrigation_service.py`. It now owns manual start/stop orchestration, direct controller commands, Nano config commands, schedule updates, pilot config/evaluation actions, OpenWeather/weather snapshot handling, pilot/weather caches, physical valve confirmation, safety session checks, irrigation summary schema/refresh, irrigation snapshot/statistics read-model builders, legacy scheduler execution, v2 scheduler execution, v2 execution status marking, and scheduler tick branch selection while the legacy Flask routes remain stable.
- Scheduler orchestration is moving into `infra/backend/scheduler_service.py`. It now owns scheduler schema bootstrap, scheduler config updates, scheduler state payload assembly, shadow job aggregation, scheduler run history formatting, V2 core summary assembly, V2 simulation chain building, V2 execution engine state, execution decision checks, scheduler run/event inserts, shadow audit event selection, V2 irrigation/X10/climate plan + execution inserts, confirmation diagnostics, legacy comparisons, and domain preflight readiness checks while the existing Flask routes and worker callers remain stable.
- `tuya`, `power_wall`, `irrigation_pilot`, `irrigation_statistics`, `home_statistics`, and `backup` now use pure payload builders instead of calling Flask route handlers from the Context Layer.
- Legacy GET endpoints remain as thin JSON wrappers over the same payload builders or context sections.
- Main command endpoints now include a `context` response hint with invalidated sections and `read_after` URLs. Example:
- Route registration has been moved out of `app.py` into `infra/backend/api_route_modules.py` for context, AI, backup, climate, scheduler, robot/X10, energy/power-wall, admin/notes, irrigation, and system read routes.
- Database access helpers now delegate to `infra/backend/database_service.py`.
- The formal endpoint contract is documented in `docs/context-api.md`.
- `scripts/smoke_backend.py` provides a repeatable backend HTTP smoke check.
- `scripts/smoke_backend.py` now enforces latency budgets for key context endpoints unless `--no-perf-budget` is used.
- `GET /api/context/ai/summary` uses the lightweight `scheduler_ai` section instead of the full scheduler payload.

```json
{
  "context": {
    "invalidated": ["irrigation"],
    "read_after": ["/api/context/irrigation"]
  }
}
```

This keeps command execution on the existing safe paths while making every command response context-aware for Web UI, mobile, and future agents.
