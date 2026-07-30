# HomeControl AI Context Pack

This directory contains the canonical working context for AI-assisted changes in
HomeControl.

Use these files before changing domain behavior:

- `module-map.md`: quick routing map from task/module to the right context
  files.
- `homecontrol-agent-guide.md`: global system rules, architecture, safe mutation
  paths, context-layer contracts, and verification expectations.
- `agent-workflow.md`: repeatable workflow for using the context pack during
  AI-assisted implementation.
- `irrigation-domain.md`: detailed irrigation domain model, command flow,
  database objects, MQTT topics, scheduler modes, pilot rules, and safety rules.
- `irrigation-scenarios.md`: concrete behavior examples and regression/eval
  cases for the irrigation module.
- `solar-domain.md` and `solar-scenarios.md`: Growatt/solar read model.
- `x10-domain.md` and `x10-scenarios.md`: Xiaomi X10 robot and weekly schedule
  behavior.
- `climate-domain.md` and `climate-scenarios.md`: Gree climate control and
  climate schedules.
- `power-wall-domain.md` and `power-wall-scenarios.md`: smart plug wall,
  always-on guard, auto-climate sync, and randomized scheduler.
- `tuya-domain.md` and `tuya-scenarios.md`: Tuya read model and switch commands.
- `performance-domain.md` and `performance-scenarios.md`: system health,
  Docker, PostgreSQL, MQTT, workers, and server power.
- `scheduler-domain.md` and `scheduler-scenarios.md`: scheduler V2 event/plan/
  execution model.
- `backup-domain.md` and `backup-scenarios.md`: backup, compare, and restore.
- `notes-admin-domain.md` and `notes-admin-scenarios.md`: notes, admin
  bootstrap, metrics, devices, and opening policies.
- `ai-domain.md` and `ai-scenarios.md`: AI proxy and remote AI node.
- `module-context-template.md`: copy this when documenting the next module.

## How To Use

When asking an AI agent to work on this repository, include this instruction:

```text
Before changing HomeControl behavior, read docs/ai/README.md and the domain
file for the affected module. Do not invent business rules. If a required rule
is missing or conflicts with code/tests, state the conflict and make the
smallest safe change.
```

For irrigation-specific work, use:

```text
Read docs/ai/irrigation-domain.md and docs/ai/irrigation-scenarios.md first.
Preserve existing safety behavior unless the task explicitly changes it.
Run the focused irrigation tests after editing.
```

## Maintenance Rule

If code changes alter domain behavior, update the matching AI context file in
the same change. The docs here are not marketing docs; they are operational
contracts for future agents and maintainers.
