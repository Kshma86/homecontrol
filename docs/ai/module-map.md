# HomeControl Module Map

Use this as the entry point when deciding which context files an AI agent should
read for a task.

## Core

Global architecture:

- `homecontrol-agent-guide.md`
- `agent-workflow.md`

Context API:

- `docs/context-api.md`
- `docs/hc-context-layer.md`

Scheduler:

- `scheduler-domain.md`
- `scheduler-scenarios.md`

## Physical And Energy Domains

Irrigation:

- `irrigation-domain.md`
- `irrigation-scenarios.md`

Solar / Growatt:

- `solar-domain.md`
- `solar-scenarios.md`

Power wall / smart plugs:

- `power-wall-domain.md`
- `power-wall-scenarios.md`

Tuya:

- `tuya-domain.md`
- `tuya-scenarios.md`

Climate / Gree:

- `climate-domain.md`
- `climate-scenarios.md`

Xiaomi X10:

- `x10-domain.md`
- `x10-scenarios.md`

## Operations

Performance and system status:

- `performance-domain.md`
- `performance-scenarios.md`

Backup and restore:

- `backup-domain.md`
- `backup-scenarios.md`

Notes and admin:

- `notes-admin-domain.md`
- `notes-admin-scenarios.md`

AI proxy and AI node:

- `ai-domain.md`
- `ai-scenarios.md`

## Task Routing

If the task mentions an endpoint, search in:

- `infra/backend/api_route_modules.py`
- the matching `*-domain.md`

If the task mentions a context section, search in:

- `infra/backend/context_service.py`
- `infra/backend/app.py`
- the matching `*-domain.md`

If the task mentions MQTT, search in:

- `infra/backend/app.py`
- the matching domain service
- apps under `apps/`

If the task mentions scheduling, read:

- `scheduler-domain.md`
- affected module domain file
- `infra/backend/scheduler_service.py`

If the task mentions hardware safety, read:

- affected module domain file
- affected scenarios file
- focused tests

## Coverage Status

Covered by this AI context pack:

- irrigation
- solar
- Xiaomi X10
- climate
- power wall
- Tuya
- performance/system status
- scheduler
- backup/restore
- notes/admin
- AI proxy/node

Not yet split into dedicated domain files:

- repository/admin source inspection helper
- startup service internals
- MQTT monitor internals
- database helper internals

These are currently covered by `homecontrol-agent-guide.md` and direct code
inspection.
