# Scheduler Scenarios And Eval Cases

## Shadow Event

Given:

- A domain job is due in shadow mode.

Expected:

- Insert event/plan/execution audit rows.
- Execution has `shadow_ready`.
- `side_effects` is false.
- No MQTT publish happens.

## Publish Domain Disabled

Given:

- V2 execution is globally enabled but target domain is not in
  `publish_domains`.

Expected:

- Domain executor does not publish.
- Simulation/preflight explains the block.

## Irrigation Preflight Active Session

Given:

- An irrigation session is running.

Expected:

- Irrigation preflight overall is `BLOCKED`.
- Check key `active_session` is blocking.

## Irrigation Pilot Analysis

Given:

- Scheduler engine has no `irrigation` in `publish_domains`.
- Irrigation pilot recommendation contains `triggered_rules`.

Expected:

- Explain the pilot rule as recommendation/evaluation data.
- Do not say V2 scheduler executed irrigation.
- If a session exists, use its `started_by` and `start_payload` to identify the
  real command owner.

## X10 Already Matching

Given:

- Desired HC-owned X10 schedule matches robot scheduler entries.

Expected:

- No publish.
- Execution confirmed with reason `robot_schedule_already_matches`.

## Climate Publish Blocked

Given:

- Climate plan exists but climate is not in publish domains.

Expected:

- Execution remains shadow/audit.
- Command payload has `shadow_only: true`.

## Suggested Tests

- Engine state maps modes to publish domains correctly.
- Simulation does not write device commands.
- Event/plan/execution idempotency prevents duplicates.
- Preflight block/warn/pass counts determine overall status.
