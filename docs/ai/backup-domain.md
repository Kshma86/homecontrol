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
- `scripts/restic_check_ai_backup.sh`
- `scripts/restore_smoke_test.sh`
- `scripts/gitea_config_status.sh`
- `scripts/gitea_config_commit.sh`
- `scripts/gitea_config_restore.sh`
- `scripts/export_gitea_config_snapshot.sh`
- `scripts/init_secrets_age_key.sh`
- `scripts/create_secrets_bundle.sh`
- `scripts/restore_secrets_bundle.sh`
- `scripts/sync_config_to_gitea.sh`
- `scripts/weekly_ai_backup.sh`
- `apps/ai-node/backup_gitea.sh`
- `scripts/systemd/homecontrol-backup.timer`
- `scripts/systemd/homecontrol-backup.service`
- `scripts/systemd/homecontrol-ai-weekly-backup.timer`
- `scripts/systemd/homecontrol-ai-weekly-backup.service`
- `scripts/systemd/homecontrol-restic-check.timer`
- `scripts/systemd/homecontrol-restic-check.service`
- `docs/backup-restore-runbook.md`
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
- `POST /api/backup/full-ai`
- `POST /api/backup/gitea/status`
- `POST /api/backup/gitea/commit`
- `POST /api/backup/gitea/restore`
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
  automations, scripts, docker-compose files, apps, backend/frontend source and
  HomeControl helper code.
- `scripts/sync_config_to_gitea.sh` pushes a filtered configuration snapshot to
  `ssh://git@192.168.1.2:2222/homecontrol/config.git`. It excludes secrets,
  `.env`, SSH keys, databases, logs, cache/runtime folders and selected local
  capture data.
- `scripts/sync_config_to_gitea.sh` can also push the same snapshot to an
  optional offsite Git remote, for example GitHub. Offsite settings are
  `git_offsite_enabled`, `git_offsite_remote`, `git_offsite_branch`,
  `git_offsite_token_file`, and `git_offsite_ssh_key`.
- HTTPS offsite pushes read the token from the configured token file through a
  temporary `GIT_ASKPASS` helper; tokens must not be placed in the remote URL.
- The Backup tab exposes a Gitea Control panel:
  `Status / Diff` runs `scripts/gitea_config_status.sh`,
  `Commit & Push` runs `scripts/gitea_config_commit.sh`, and
  `Restore to Staging` runs `scripts/gitea_config_restore.sh`.
- Gitea restore is non-destructive: it clones the selected branch/tag/commit to
  `/srv/docker/homecontrol/restore_staging/gitea-config-*` and never overwrites
  live HomeControl files.
- Restic from the HC server is for restore-grade HC snapshots: the full
  HomeControl tree, database dumps, Docker volumes and media files.
- Daily backup treats the remote restic target as best-effort: if the AI server
  is sleeping or the HDD is unavailable, the local archive still succeeds and
  the restic step is logged as skipped.
- Weekly AI HDD backup uses `scripts/weekly_ai_backup.sh`: it wakes the AI
  server through the backend AI-node API only when SSH was not reachable at
  start, waits for SSH, refreshes the encrypted secrets bundle when the age
  layer is ready, pushes the filtered Gitea config snapshot, runs
  `scripts/backup_hc.sh` with `RESTIC_REQUIRED=true`, then requests AI-server
  shutdown only if the backup had to wake the AI server.
- While waiting for SSH, the weekly/full backup logs progress every 30 seconds
  and repeats the wake/Wake-on-LAN request every 60 seconds until the 15-minute
  timeout expires.
- If the AI server was already reachable when the weekly/full backup started,
  the backup leaves it running. An explicit deferred shutdown request from the
  AI page is still honored after the backup completes successfully.
- The weekly job also asks the AI server to run `apps/ai-node/backup_gitea.sh`
  when that helper exists in the remote `~/homecontrol-ai-node` directory.
- Monthly `homecontrol-restic-check.timer` runs `scripts/restic_check_ai_backup.sh`
  to verify that the restic repository is readable.
- `scripts/restore_smoke_test.sh` is the non-destructive restore proof: it
  checks the latest local archive, Gitea reachability and, when enabled, a
  small restic restore into `/tmp`.
- AI-server Gitea data lives on the remote host; back it up with a Gitea dump or
  an AI-side local backup job, not as a HC-server restic source path.
- `scripts/check_ai_backup_target.sh` verifies SSH access, mount availability,
  write permission, and creates the expected AI HDD directories:
  `database`, `config`, `files`, `restic/homecontrol`, and `gitea`.
- `scripts/install_restic_backup_prereqs.sh` is a one-time HC-host root helper
  that installs `restic` and creates `/etc/homecontrol/restic-password`.
- Local `homecontrol_*.tar.gz` archives remain as a manual/scheduled fallback
  and keep the existing inspect, compare and staging restore workflow.
- Secrets are handled as a separate encrypted layer. The cleartext source files
  stay outside Git/Gitea, while `scripts/create_secrets_bundle.sh` packs the
  manifest-defined secret paths into `secrets/homecontrol-secrets-*.tar.gz.age`.
  Only encrypted `.age` files, checksums, the public age recipient and the
  manifest are allowed into the Gitea/GitHub snapshot.
- `scripts/init_secrets_age_key.sh` creates the local age identity under
  `infra/ssh/homecontrol-secrets-age-key.txt` and writes the public recipient to
  `secrets/age-recipient.txt`. The identity private key must be stored outside
  the HC machine too, for example in a password manager or offline emergency
  note.
- `scripts/restore_secrets_bundle.sh` decrypts the latest secrets bundle to
  staging by default and writes to `/` only with `--apply --confirm`.

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
