# AI Agent Workflow

Use this workflow for efficient AI-assisted HomeControl work.

## Start Of Task

1. Read `docs/ai/README.md`.
2. Read `docs/ai/module-map.md`.
3. Read `docs/ai/homecontrol-agent-guide.md`.
4. Read the domain file for the affected module.
5. Read the matching scenario/eval file if it exists.
6. Inspect the implementation and focused tests before editing.

For irrigation work, read:

- `docs/ai/irrigation-domain.md`
- `docs/ai/irrigation-scenarios.md`
- `infra/backend/irrigation_service.py`
- `infra/backend/tests/test_irrigation_service.py`

## Rule Priority

When sources disagree, use this priority:

1. Explicit user request in the current task.
2. Safety-critical code behavior that protects hardware or prevents duplicate
   execution.
3. Existing tests.
4. Domain context files under `docs/ai/`.
5. Existing docs under `docs/`.
6. Naming conventions or inferred intent.

If the user request conflicts with a safety rule, state the conflict before
changing behavior.

## Before Editing

Write down the behavioral surface:

- affected endpoint or worker;
- affected domain service method;
- durable tables/views;
- MQTT command or telemetry topic;
- context sections that must be invalidated;
- focused tests that should pass or be added.

## During Editing

- Change the smallest set of files that owns the behavior.
- Keep route wrappers thin.
- Prefer domain service changes over route-level branching.
- Do not add direct device side effects in read-model builders.
- Do not change scheduler ownership by accident.
- Update `docs/ai/<module>-domain.md` when behavior changes.
- Update `docs/ai/<module>-scenarios.md` when a new edge case is discovered.

## After Editing

Run the narrowest meaningful verification first. For backend-only changes:

```bash
python3 -m unittest infra.backend.tests.test_irrigation_service
python3 -m unittest infra.backend.tests.test_scheduler_service
python3 -m unittest infra.backend.tests.test_context_service_contract
python3 -m unittest infra.backend.tests.test_command_service
```

For frontend changes, run the existing frontend checks or start the Vite app and
inspect the affected screen.

For running backend instances:

```bash
python3 scripts/smoke_backend.py --base-url http://127.0.0.1:5000
```

## When To Add A Scenario

Add or update a scenario when:

- a bug was caused by misunderstood business behavior;
- a user corrects an AI answer more than once on the same rule;
- a state transition is added or renamed;
- a scheduler condition changes;
- a hardware safety behavior changes;
- a new telemetry source changes decisions;
- a new V2 execution/audit status appears.

## When To Add A Test

Add a test when:

- behavior is safety-critical;
- a command publishes MQTT;
- a session status changes;
- one-run-per-day or duplicate-execution behavior changes;
- context invalidation changes;
- pilot/navigator rule precedence changes;
- V2 shadow versus execution ownership changes.

## Good Task Prompt Pattern

```text
Task: <specific change>

Read:
- docs/ai/README.md
- docs/ai/homecontrol-agent-guide.md
- docs/ai/<module>-domain.md
- docs/ai/<module>-scenarios.md

Constraints:
- Preserve existing safety rules unless explicitly changed.
- Do not invent business rules.
- Add/update focused tests for changed behavior.
- Update the AI context docs if behavior changes.
```

## Good Final Report Pattern

Report:

- files changed;
- behavior changed;
- tests run;
- any unverified risk.

Keep it short, but include enough detail that the next AI or human can continue
without reconstructing the whole task.
