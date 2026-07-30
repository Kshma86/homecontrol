# Module Context Template

Copy this file to `docs/ai/<module>-domain.md` when documenting another
HomeControl module.

## Scope

Describe what the module controls or observes.

Primary implementation:

- `path/to/service.py`
- `path/to/routes.py`
- `path/to/tests.py`
- `path/to/migrations.sql`

## Ownership

- Durable truth:
- Mutation owner:
- Read model/context section:
- External device/API boundary:

## Safety Principles

- List invariants that must not be broken.
- List concurrency or active-session rules.
- List hardware/device protection rules.
- List side-effect boundaries.

## Environment

- `ENV_NAME`: default and meaning.

## MQTT Topics Or External APIs

- Topic/API:
- Payload shape:
- Confirmation/ack behavior:

## API Endpoints

Mutation endpoints:

- `METHOD /path`

Read endpoints:

- `METHOD /path`

## Database Objects

Tables:

- `schema.table`

Views:

- `schema.view`

## Domain Rules

Document rules as direct, testable statements.

## Lifecycle Or State Machine

Statuses:

- `status`: meaning.

Transitions:

- `from -> to`: trigger and side effects.

## Scheduler Rules

- When the scheduler may act.
- When it must not act.
- How duplicate runs are prevented.
- How stop/completion is marked.

## Context Payload

Context section:

- Fields emitted.
- Cache TTL category.
- Invalidation triggers.

## Scenarios

Create a separate `docs/ai/<module>-scenarios.md` file with examples:

- Given:
- Expected:
- Current/needed unit test:

## Verification

Focused tests:

```bash
python3 -m unittest path.to.test_module
```

Smoke tests:

```bash
python3 scripts/smoke_backend.py --base-url http://127.0.0.1:5000
```

## Do Not

- List known dangerous shortcuts or common AI mistakes.
