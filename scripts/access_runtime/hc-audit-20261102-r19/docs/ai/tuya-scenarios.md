# Tuya Scenarios And Eval Cases

## Empty State

Given:

- No active Tuya entities exist.

Expected:

- `devices`, `state_rows`, and `recent_measurements` are empty.
- Summary counts are zero.

## State Map

Given:

- Active Tuya entity has state rows for numeric, boolean, text, and JSON keys.

Expected:

- Device `state` map uses the first non-null value in this order:
  `v_num`, `v_bool`, `v_text`, `v_json`.

## Switch By Entity Id

Given:

- `/api/tuya/command` receives an entity id and boolean value.

Expected:

- Finds active Tuya entity.
- Publishes to `homecontrol/cmd/tuya/{entity_name}/switch`.
- Invalidates `tuya` and `power_wall`.

## Unknown Entity

Given:

- Command references missing or inactive Tuya entity.

Expected:

- Return not-found behavior.
- Do not publish.

## Suggested Tests

- State value precedence.
- Command by name and by id.
- Cache invalidation for `tuya_state` and `power_wall_state`.
