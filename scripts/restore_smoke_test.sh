#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
BACKUP_ROOT="${BACKUP_ROOT:-$BASE/backups}"
SETTINGS_FILE="$BACKUP_ROOT/backup_settings.json"
LOG_FILE="$BACKUP_ROOT/backup.log"
TMP_ROOT="$(mktemp -d /tmp/hc-restore-smoke.XXXXXX)"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

setting() {
  local key="$1"
  local default="$2"
  python3 - "$SETTINGS_FILE" "$key" "$default" <<'PY' 2>/dev/null || printf '%s\n' "$default"
import json
import sys
path, key, default = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    value = data.get(key, default)
except Exception:
    value = default
if isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

log() {
  mkdir -p "$BACKUP_ROOT"
  echo "[$(date '+%F %T')] $*" | tee -a "$LOG_FILE"
}

fail() {
  log "HIBA: $*"
  exit 1
}

latest_archive() {
  find "$BACKUP_ROOT" -maxdepth 1 -type f -name 'homecontrol_*.tar.gz' -printf '%T@ %p\n' \
    | sort -nr \
    | awk 'NR == 1 {print $2}'
}

ARCHIVE="${1:-$(latest_archive)}"
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || fail "Nincs ellenőrizhető helyi archívum"

log "== Restore smoke test indul: $ARCHIVE =="
tar -tzf "$ARCHIVE" >/dev/null
tar -xzf "$ARCHIVE" -C "$TMP_ROOT" --wildcards '*/MANIFEST.txt' '*/SHA256SUMS.txt'
find "$TMP_ROOT" -name MANIFEST.txt -type f -print -quit >/dev/null \
  || fail "MANIFEST.txt nem található az archívumban"
find "$TMP_ROOT" -name SHA256SUMS.txt -type f -print -quit >/dev/null \
  || fail "SHA256SUMS.txt nem található az archívumban"
log "-- Helyi archívum listázható és a manifest/checksum fájlok olvashatók"

GIT_ENABLED="$(setting git_enabled true)"
GITEA_REMOTE="${GITEA_REMOTE:-ssh://git@$(setting ai_backup_host 192.168.1.2):2222/$(setting git_repository homecontrol/config).git}"
GITEA_SSH_KEY="${GITEA_SSH_KEY:-$(setting ai_backup_ssh_key /srv/docker/homecontrol/infra/ssh/ai_node_key)}"
if [ "$GIT_ENABLED" = "true" ]; then
  export GIT_SSH_COMMAND="ssh -i $GITEA_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
  git ls-remote "$GITEA_REMOTE" HEAD refs/heads/main >/dev/null \
    && log "-- Gitea repository elérhető: $GITEA_REMOTE" \
    || fail "A Gitea repository nem elérhető: $GITEA_REMOTE"
fi

RESTIC_ENABLED="$(setting restic_enabled false)"
if [ "$RESTIC_ENABLED" = "true" ]; then
  AI_BACKUP_HOST="$(setting ai_backup_host 192.168.1.2)"
  AI_BACKUP_USER="$(setting ai_backup_user a)"
  AI_BACKUP_MOUNT="$(setting ai_backup_mount /mnt/hc-backup)"
  RESTIC_REPOSITORY="$(setting restic_repository sftp:${AI_BACKUP_USER}@${AI_BACKUP_HOST}:${AI_BACKUP_MOUNT}/restic/homecontrol)"
  RESTIC_PASSWORD_FILE="$(setting restic_password_file /etc/homecontrol/restic-password)"
  [ -f "$RESTIC_PASSWORD_FILE" ] || fail "Nincs restic password file: $RESTIC_PASSWORD_FILE"
  export RESTIC_REPOSITORY
  export RESTIC_PASSWORD_FILE
  export RESTIC_CACHE_DIR="$TMP_ROOT/restic-cache"
  RESTIC_ARGS=(-o "sftp.command=ssh -i $GITEA_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new ${AI_BACKUP_USER}@${AI_BACKUP_HOST} -s sftp")
  restic "${RESTIC_ARGS[@]}" snapshots --tag homecontrol >/dev/null
  restic "${RESTIC_ARGS[@]}" restore latest --target "$TMP_ROOT/restic-restore" --include '/srv/docker/homecontrol/backups/homecontrol_*.tar.gz' >/dev/null
  find "$TMP_ROOT/restic-restore" -type f -name 'homecontrol_*.tar.gz' -print -quit >/dev/null \
    || fail "A restic restore próba nem hozott vissza archívumot"
  log "-- Restic latest snapshotból próba-visszaállítás sikeres"
fi

log "== Restore smoke test kész =="
