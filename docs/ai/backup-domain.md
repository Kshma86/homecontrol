# Backup Domain Context

## Scope

The backup module creates, lists, inspects, compares, configures, and restores
HomeControl backup archives. It also exposes the prepared backup plan for the
next AI-server HDD setup: Git/Gitea for human-edited config and restic for full
system-state snapshots.

Primary implementation:

- `infra/backend/backup_service.py`
- `infra/backend/api_route_modules.py`
- `scripts/backup_hc.sh`
- `scripts/check_ai_backup_target.sh`
- `scripts/install_restic_backup_prereqs.sh`
- `scripts/systemd/homecontrol-backup.timer`
- `scripts/systemd/homecontrol-backup.service`
- `infra/backend/tests/test_backup_service_payloads.py`

## Ownership

- Backup files: `HC_BACKUP_DIR`, default `/srv/docker/homecontrol/backups`.
- AI backup HDD mount on the AI server: `/mnt/hc-backup`, ext4 label
  `HC_BACKUP`.
- Restic repository default:
  `sftp:a@192.168.1.2:/mnt/hc-backup/restic/homecontrol`.
- Gitea target default: `http://192.168.1.2:3002`, repository
  `homecontrol/config`.
- Settings file: `backup_settings.json` inside backup root.
- Restore staging: `HC_RESTORE_STAGING_DIR`, default
  `/srv/docker/homecontrol/restore_staging`.
- Context section: `backup`.

## API Endpoints

Read endpoints:

- `GET /api/context/backup`
- `GET /api/backup`
- `GET /api/backup/<backup_name>/contents`
- `GET /api/backup/<backup_name>/compare?path=...`

Mutation endpoints:

- `PUT /api/backup/settings`
- `POST /api/backup/create`
- `POST /api/backup/restore`

## Settings

Defaults:

- include PostgreSQL, apps, infra, Zigbee2MQTT, Home Assistant, scripts, Docker
  metadata;
- include Docker volumes, media and Gitea data in the restic plan;
- enable Git/Gitea version tracking for Home Assistant config, automations,
  scripts and docker-compose files;
- prepare restic snapshots to the AI-server HDD repository; the setting is
  opt-in until the HDD mount and password file are ready;
- restic retention keeps 14 daily, 8 weekly and 6 monthly snapshots;
- retention is 14 days;
- schedule is enabled at `02:15`.

`schedule_time` must be `HH:MM`.

## Backup Layers

- Git/Gitea is for versioned text/config: Home Assistant configuration,
  automations, scripts, docker-compose files and HomeControl helper code.
- Restic from the HC server is for restore-grade HC snapshots: the full
  HomeControl tree, database dumps, Docker volumes and media files.
- Daily backup treats the remote restic target as best-effort: if the AI server
  is sleeping or the HDD is unavailable, the local archive still succeeds and
  the restic step is logged as skipped.
- Weekly AI HDD backup uses `scripts/weekly_ai_backup.sh`: it wakes the AI
  server through the backend AI-node API, waits for SSH, runs
  `scripts/backup_hc.sh` with `RESTIC_REQUIRED=true`, then requests AI-server
  shutdown by default.
- AI-server Gitea data lives on the remote host; back it up with a Gitea dump or
  an AI-side local backup job, not as a HC-server restic source path.
- `scripts/check_ai_backup_target.sh` verifies SSH access, mount availability,
  write permission, and creates the expected AI HDD directories:
  `database`, `config`, `files`, `restic/homecontrol`, and `gitea`.
- `scripts/install_restic_backup_prereqs.sh` is a one-time HC-host root helper
  that installs `restic` and creates `/etc/homecontrol/restic-password`.
- Local `homecontrol_*.tar.gz` archives remain as a manual/scheduled fallback
  and keep the existing inspect, compare and staging restore workflow.

## Archive Rules

- Archive names must end with `.tar.gz`.
- `safe_path()` strips directory components and requires the resolved parent to
  be the backup root.
- Contents are limited by request limit, default 500 rows.
- `zigbee2mqtt/data/...` is treated as a logical top-level component.

## Restore Rules

- Restore can target staging or actual configured roots depending on mode.
- Path selection must remain inside known restore targets.
- Restore is the riskiest operation in this module; preserve path sanitization
  and confirmation requirements.

## Safety Rules

- Do not allow path traversal from backup name or member path.
- Do not restore arbitrary archive members outside known roots.
- Do not silently change backup timer files without invalidating `backup`.
- Do not run destructive restore behavior unless the route's confirmation model
  allows it.
