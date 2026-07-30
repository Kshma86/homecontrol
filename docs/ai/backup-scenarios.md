# Backup Scenarios And Eval Cases

## Missing Backup Directory

Given:

- No backup directory is readable.

Expected:

- Latest info returns `ok: false`.
- Payload explains backup directory is unavailable.

## Safe Archive Path

Given:

- User passes `../../secret.tar.gz`.

Expected:

- Only basename is considered.
- Archive must exist inside backup root.
- Otherwise raise `backup archive not found`.

## Save Settings

Given:

- Settings update includes `schedule_time = "03:10"`.

Expected:

- Settings file is written.
- Timer file is regenerated with matching `OnCalendar`.
- Backup context is invalidated by route wrapper.

## Compare Binary File

Given:

- Backup member or current file appears binary.

Expected:

- Do not emit huge or invalid text diffs.
- Return binary/unsupported comparison details.

## Suggested Tests

- Path traversal attempts are rejected.
- Timer parsing and writing preserve HH:MM.
- Restore selection maps only to known roots.
