# HomeControl Agent Guide

This is the global context for AI agents working on HomeControl.

## System Shape

HomeControl is a local home automation control system with these major pieces:

- Flask backend under `infra/backend/`
- React/Vite frontend under `infra/frontend/`
- PostgreSQL schema and migrations under `infra/db/`
- MQTT ingest and device bridge apps under `apps/`
- Home Assistant configuration under `homeassistant/config/`
- Shared read models exposed through the Context Layer

The backend is the main orchestration point. Domain services own behavior.
Routes should stay thin.

## Architectural Rules

- PostgreSQL is the durable source of truth.
- MQTT is the device command and telemetry transport.
- The Context Layer is a read-through in-memory read model, not the source of
  truth.
- Mutations must go through domain-safe command endpoints or domain services.
- Command responses should include context invalidation metadata when state
  changes.
- Existing compatibility endpoints should remain stable unless the task
  explicitly removes them.
- Prefer extracting pure payload/domain builders over calling Flask route
  handlers from internal services.

## Key Files

- `infra/backend/app.py`: application wiring, environment config, service
  construction, topic definitions, route registration.
- `infra/backend/api_route_modules.py`: Flask route wrappers.
- `infra/backend/context_service.py`: shared context cache and AI summary.
- `infra/backend/command_service.py`: command-to-context invalidation mapping.
- `infra/backend/scheduler_service.py`: unified scheduler, V2 event/plan/
  execution audit and execution orchestration.
- `infra/backend/schema_service.py`: backend schema bootstrap helpers.
- `infra/db/*.sql`: migrations and durable schema/data changes.
- `infra/backend/tests/`: Python unit tests.

## Context Layer Contract

Read model endpoints:

- `GET /api/context`
- `GET /api/context?full=1`
- `GET /api/context?sections=weather,irrigation`
- `GET /api/context/<section>`
- `GET /api/context/ai/summary`
- `POST /api/context/invalidate`

Default lightweight sections include:

- `weather`
- `irrigation`
- `climate`
- `robot`
- `power_wall`
- `solar`
- `tuya`
- `backup`
- `notes`

Expensive or lazy sections include:

- `scheduler`
- `scheduler_ai`
- `irrigation_pilot`
- `irrigation_statistics`
- `climate_power_history`
- `climate_schedules`
- `performance`
- `home_statistics`

Mutation responses should include:

```json
{
  "context": {
    "invalidated": ["irrigation"],
    "read_after": ["/api/context/irrigation"]
  }
}
```

## Scheduler Model

The scheduler has legacy, shadow, plan-only, and V2 execution concepts.

Important V2 tables:

- `hc.event`: immutable facts.
- `hc.plan`: intended actions.
- `hc.execution`: execution/audit records.

V2 shadow records must not publish device commands. Actual publishing is only
allowed when the scheduler engine and per-domain feature flags enable it.

## Agent Operating Rules

- Read the affected domain service and tests before editing behavior.
- Do not infer physical-device semantics from names alone; verify with existing
  code, schema, MQTT topics, or tests.
- Preserve safety checks around pumps, valves, manual overrides, scheduler
  ownership, and active sessions.
- Keep changes narrow and consistent with existing service patterns.
- If behavior changes, add or update focused tests.
- If a command mutates state, invalidate the relevant context section.
- If adding a new read model, document its context section and cache behavior.
- If adding a new database object, prefer a migration in `infra/db/` and keep
  bootstrap code consistent if similar tables are already bootstrapped there.

## Verification

Use focused tests first:

```bash
python3 -m unittest infra.backend.tests.test_irrigation_service
python3 -m unittest infra.backend.tests.test_scheduler_service
python3 -m unittest infra.backend.tests.test_context_service_contract
python3 -m unittest infra.backend.tests.test_command_service
```

Broader backend smoke:

```bash
python3 scripts/smoke_backend.py --base-url http://127.0.0.1:5000
```

If a test cannot run because services or dependencies are unavailable, report
that explicitly and mention which behavior was not verified.

## Do Not

- Do not bypass domain services by publishing MQTT from unrelated code.
- Do not update context caches without also updating durable state when the
  action is a real mutation.
- Do not mark a V2 shadow/audit execution as a real publish.
- Do not remove legacy compatibility routes unless requested.
- Do not silently change schedule semantics such as one-run-per-day guards,
  stop authority, or active-session locking.
