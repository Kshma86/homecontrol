# Scheduler Domain Context

## Scope

The scheduler module unifies time-based actions for irrigation, Xiaomi X10, and
climate. It supports legacy observation, V2 shadow/audit, and selective V2
execution.

Primary implementation:

- `infra/backend/scheduler_service.py`
- `infra/backend/irrigation_service.py`
- `infra/backend/climate_service.py`
- `infra/backend/robot_service.py`
- `infra/db/003_hc_v2_core.sql`
- `infra/db/004_v2_irrigation_plan_shadow_backfill.sql`
- `infra/db/005_v2_irrigation_execution_shadow_backfill.sql`
- `infra/db/006_v2_x10_plan_execution_shadow_backfill.sql`
- `infra/db/007_v2_scheduler_modes_and_executor.sql`
- `infra/db/008_v2_x10_executor_mode.sql`
- `infra/backend/tests/test_scheduler_service.py`

## Ownership

- Durable V2 truth: `hc.event`, `hc.plan`, `hc.execution`.
- Scheduler config: `hc.scheduler_config`.
- Domain command ownership remains with each domain service.
- Context sections: `scheduler`, `scheduler_ai`.

## API Endpoints

Read/mutation endpoints:

- `GET /api/scheduler/state`
- `PUT /api/scheduler/config`
- `POST /api/v2/simulate/scheduler`
- `GET /api/context/scheduler`
- `GET /api/context/scheduler_ai`

## V2 Core Model

- `hc.event`: immutable facts, what happened and when.
- `hc.plan`: intended action before execution.
- `hc.execution`: command/audit/confirmation result.

Shadow/audit rows must have no device side effects.

## Engine Rules

The scheduler engine decides publish domains from:

- scheduler mode;
- global V2 feature flag;
- per-domain allow flags.

Known domains:

- `irrigation`
- `xiaomi_x10`
- `climate`

Supported actions:

- irrigation: `water_start`, `water_stop`
- X10: `clean_start`
- climate: `climate_set`

## Shadow Job Rules

Shadow jobs aggregate from domain schedule sources:

- irrigation schedules;
- X10 HC-owned weekly schedules;
- climate schedule rules.

Shadow jobs record what would happen and create audit event/plan/execution rows
without publishing.

## Execution Rules

- A domain can publish only when present in `engine.publish_domains`.
- Domain preflight checks report `READY`, `WARN`, or `BLOCKED`.
- Common preflight includes database and MQTT connectivity.
- Domain-specific preflight adds hardware/scheduler readiness checks.
- Execution records must accurately distinguish:
  - `shadow_ready`
  - `confirmed`
  - `failed`
  - `blocked`
  - `skipped`

## Domain Notes

Irrigation:

- manual valve guard and active session block execution;
- V2 effective stop policy resolves stop authority;
- pilot/navigator may alter or recommend duration.
- watering analysis must connect scheduler engine state with
  `irrigation_pilot` decision state and concrete irrigation sessions;
- V2 can only be called the command owner when `engine.publish_domains`
  contains `irrigation`.

X10:

- validates desired weekly schedule rows;
- blocks publish when robot appears active;
- avoids publish when robot schedule already matches.

Climate:

- validates command values;
- may auto-sync power wall on power commands;
- uses shadow/audit rows when publish is disabled.

## Context Payloads

`scheduler` includes detailed state, jobs, run history, V2 core summary,
simulation/preflight details, and diagnostics.

`scheduler_ai` is the lightweight AI section and should avoid expensive history
payloads where possible.

## Safety Rules

- Do not convert shadow/audit rows into publishing code accidentally.
- Do not publish for a domain unless both scheduler mode and feature flags allow
  it.
- Do not skip domain preflight checks when enabling V2 execution.
- Do not make simulated chains mutate device state.
