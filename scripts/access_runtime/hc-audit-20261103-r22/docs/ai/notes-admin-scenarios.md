# Notes And Admin Scenarios And Eval Cases

## Create Note

Given:

- Type is `issues`.
- Text is non-empty.

Expected:

- Insert note.
- Return refreshed grouped notes.
- Invalidate `notes`.

## Invalid Note Type

Given:

- Type is `todo`.

Expected:

- Reject with `type must be issues or requests`.
- Do not insert.

## Empty Note Update

Given:

- Update body contains no `text`, `comment`, or `done`.

Expected:

- Reject with `nothing to update`.

## Create Metric

Given:

- Metric key is present and value type is `num`.

Expected:

- Upsert metric.
- Invalidate power wall, Tuya, irrigation, and home statistics contexts.

## Invalid Device Platform

Given:

- Device create receives platform `cloud_only`.

Expected:

- Reject with `invalid platform`.

## Suggested Tests

- Notes grouped by `issues` and `requests`.
- Note update validates empty text.
- Metric/device admin mutations invalidate all dependent contexts.
