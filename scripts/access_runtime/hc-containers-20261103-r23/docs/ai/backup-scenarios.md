# Backup Scenarios And Eval Cases

## F6 local implementation scenarios (not deployed)

- Web create/full/Git commit returns 202 with a queued run ID. No backend Docker
  dump or tar is executed. Only the matching completed job reports success.
- Settings/lock/request/checksum, `.partial`, and a new final archive without a
  matching commit receipt never qualify as latest verified backup.
- A remote target failure preserves the last good local archive and that
  target's previous success timestamp, while the job reports failure.
- Origin push failure still attempts offsite, local archive and required restic;
  offsite or Gitea dump failures still allow the mandatory backup attempt.
- Dump/tar kill, disk-full and permission errors never publish a completed
  archive or trigger retention before a verified replacement exists.
- Parent kill leaves the inherited lock held until the worker also exits.
- Large/single-line/rotated logs use bounded tail reads. Missing lock probes
  create no file; read permission failure is unknown, not confirmed unlocked.
- System-scope install disables the exact two duplicate user timers and preserves
  operator schedules; failed installation restores the saved unit state.

Evidence and deployment limits: [HC F6 backups](../hc-f6-backups.md).
The remaining legacy scenarios below still describe deployed r2 where applicable.

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
