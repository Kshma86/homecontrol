#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
BACKUP_ROOT="${BACKUP_ROOT:-$BASE/backups}"
SETTINGS_FILE="$BACKUP_ROOT/backup_settings.json"
LOG_FILE="$BACKUP_ROOT/backup.log"
TMP_ROOT="/tmp/hc_backup"

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

RESTIC_ENABLED="$(setting restic_enabled false)"
AI_BACKUP_HOST="$(setting ai_backup_host 192.168.1.2)"
AI_BACKUP_USER="$(setting ai_backup_user a)"
AI_BACKUP_MOUNT="$(setting ai_backup_mount /mnt/hc-backup)"
AI_BACKUP_SSH_KEY="$(setting ai_backup_ssh_key /srv/docker/homecontrol/infra/ssh/ai_node_key)"
RESTIC_REPOSITORY="$(setting restic_repository sftp:${AI_BACKUP_USER}@${AI_BACKUP_HOST}:${AI_BACKUP_MOUNT}/restic/homecontrol)"
RESTIC_PASSWORD_FILE="$(setting restic_password_file /etc/homecontrol/restic-password)"

if [ "$RESTIC_ENABLED" != "true" ]; then
  log "== Restic check kihagyva: restic nincs engedélyezve =="
  exit 0
fi

command -v restic >/dev/null 2>&1 || fail "A restic nincs telepítve"
command -v ssh >/dev/null 2>&1 || fail "Az ssh kliens nincs telepítve"
[ -n "$RESTIC_REPOSITORY" ] || fail "Nincs restic_repository beállítva"
[ -f "$RESTIC_PASSWORD_FILE" ] || fail "Nincs restic password file: $RESTIC_PASSWORD_FILE"

export RESTIC_REPOSITORY
export RESTIC_PASSWORD_FILE
export RESTIC_CACHE_DIR="$TMP_ROOT/restic-check-cache"
mkdir -p "$RESTIC_CACHE_DIR"

if [ -n "$AI_BACKUP_SSH_KEY" ] && [ -f "$AI_BACKUP_SSH_KEY" ]; then
  RESTIC_ARGS=(-o "sftp.command=ssh -i $AI_BACKUP_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new ${AI_BACKUP_USER}@${AI_BACKUP_HOST} -s sftp")
  SSH_BASE=(ssh -i "$AI_BACKUP_SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${AI_BACKUP_USER}@${AI_BACKUP_HOST}")
else
  RESTIC_ARGS=(-o "sftp.command=ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new ${AI_BACKUP_USER}@${AI_BACKUP_HOST} -s sftp")
  SSH_BASE=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${AI_BACKUP_USER}@${AI_BACKUP_HOST}")
fi

log "== Restic check indul: $RESTIC_REPOSITORY =="
"${SSH_BASE[@]}" "test -d '${AI_BACKUP_MOUNT}/restic/homecontrol'" \
  || fail "Az AI restic repo könyvtár nem elérhető: ${AI_BACKUP_MOUNT}/restic/homecontrol"

restic "${RESTIC_ARGS[@]}" snapshots --tag homecontrol >/dev/null
restic "${RESTIC_ARGS[@]}" check

log "== Restic check kész =="
