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

HC-07 is implemented in the working source and is **not deployed** over the
current `hc-audit-20261022-r1` release. Before a later deployment, run the
explicit 059/060 migrations with `migrate_hc07.py`; the affected startup paths
only check the migration journal and schema compatibility. Existing disabled
inventory, scheduler modes and historical climate rules are not rewritten at
startup. Unsupported legacy scheduler modes require an explicit operator
decision; startup never promotes them to `v2_execute_all`. First-install seed
is separate, insert-only, once journalled, and refused on existing installations.
See `docs/hc07-schema-migrations.md` for restore, HC-38 and rollback limits.

- Durable V2 truth: `hc.event`, `hc.plan`, `hc.execution`.
- Scheduler config: `hc.scheduler_config`.
- Domain command ownership remains with each domain service.
- Context sections: `scheduler`, `scheduler_ai`.

## Worker And Failure Boundaries (HC-02)

`StartupService` starts one `irrigation-safety` thread and one serial
`scheduler` thread when `HC_ENABLE_SAFETY_WORKER` is enabled. They are started
once per process; no thread/task is created per scheduler tick. Initial stop
checks are attempted before scheduler work is released.

- Safety pass: close-only session recovery, V2 effective stop, generic overdue
  sessions, no-water detection.
  Each callback has independent exception handling and a named error log.
- Scheduler pass: existing scheduler audit, irrigation starts/solar-pump tick,
  X10 weekly synchronization. Each callback has independent exception handling.
  A slow opening can delay later scheduler work, but not stop supervision.
- The combustion/window-guard pair also has separate exception boundaries:
  an exception constructing/running combustion cannot skip WindowGuard.

The scheduler poll setting remains 5 seconds by default (minimum 1 second).
Both loops sleep after their own work. Stop detection latency is therefore
bounded by its own pass duration and poll sleep under responsive dependencies,
rather than by the scheduler's opening confirmation waits. This does not
guarantee a hard end-to-end deadline for unbounded DB/MQTT I/O or motor travel.

Valve stop intent cancels old OPEN retries and prevents new OPEN publications
while closing. This is process-local ordering to make the worker split safe;
HC-04 supplies a separate short DB transaction shared by manual/V2/legacy
starts: a session-table lock, active-session recheck and `starting` insertion.
Scheduled admission rechecks eligibility and consumes the DB-local schedule
day in that same transaction; a concurrent loser neither publishes nor
advances `last_started_on`. The transaction is committed before MQTT waits.
DB/lock/commit uncertainty fails closed and can be reconciled by HC-03.
No schema change is required; keep one active controller because command,
startup-recovery and worker ownership are still process-local. HC-03 supplies startup/periodic
close-only recovery using persisted per-session retry slots and backoff. It
runs regardless of the V2 domain/day gate and never replays OPEN. Existing
`physical_manual` sessions remain outside automatic recovery. A V2 failed stop
is retried by this shared recovery path; the V2 bookkeeping branch itself does
not bypass the bounded budget. Recovery of an unconfirmed start does not
mark watering successful or rebuild missing scheduler audit rows.
The existing audit persistence/publication path is retained (HC-08), including
its failure/reconciliation limits; stopping does not wait for audit success.
HC-05 safety-publish retry and HC-09 transport-result semantics are unchanged.
The existing pilot skip/audit path also remains outside the start reservation;
HC-04 does not repair missing event/plan/execution rows (HC-08).

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
