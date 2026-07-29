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

api_post() {
  local path="$1"
  local body="$2"
  (
    cd "$BASE/infra"
    docker compose exec -T backend python - "$path" "$body" <<'PY'
import json
import sys
from urllib.request import Request, urlopen

path, body = sys.argv[1], sys.argv[2]
request = Request(
    f"http://127.0.0.1:5000{path}",
    data=body.encode("utf-8"),
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urlopen(request, timeout=30) as response:
    print(response.read().decode("utf-8"))
PY
  )
}

RESTIC_ENABLED="$(setting restic_enabled false)"
AI_BACKUP_HOST="$(setting ai_backup_host 192.168.1.2)"
AI_BACKUP_USER="$(setting ai_backup_user a)"
AI_BACKUP_MOUNT="$(setting ai_backup_mount /mnt/hc-backup)"
AI_BACKUP_SSH_KEY="$(setting ai_backup_ssh_key /srv/docker/homecontrol/infra/ssh/ai_node_key)"
RESTIC_REPOSITORY="$(setting restic_repository sftp:${AI_BACKUP_USER}@${AI_BACKUP_HOST}:${AI_BACKUP_MOUNT}/restic/homecontrol)"
RESTIC_PASSWORD_FILE="$(setting restic_password_file /etc/homecontrol/restic-password)"
AI_CHECK_WAKE="${AI_CHECK_WAKE:-true}"
AI_CHECK_WAIT_SECONDS="${AI_CHECK_WAIT_SECONDS:-900}"
AI_CHECK_SHUTDOWN_AFTER="${AI_CHECK_SHUTDOWN_AFTER:-true}"
AI_CHECK_POWER_OFF_DELAY_SECONDS="${AI_CHECK_POWER_OFF_DELAY_SECONDS:-300}"
AI_WAS_ONLINE="false"
AI_WOKEN_BY_CHECK="false"

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

shutdown_if_woken() {
  local status=$?
  if [ "$AI_WOKEN_BY_CHECK" = "true" ] && [ "$AI_CHECK_SHUTDOWN_AFTER" = "true" ]; then
    log "-- AI szerver leállítás kérése restic check után"
    api_post "/api/ai/node/command" "{\"action\":\"shutdown\",\"schedule_power_off_on_failure\":true,\"power_off_delay_sec\":${AI_CHECK_POWER_OFF_DELAY_SECONDS}}" \
      || log "-- AI shutdown API nem válaszolt"
  fi
  exit "$status"
}
trap shutdown_if_woken EXIT

log "== Restic check indul: $RESTIC_REPOSITORY =="
if "${SSH_BASE[@]}" "true" >/dev/null 2>&1; then
  AI_WAS_ONLINE="true"
else
  log "-- AI szerver SSH nem elérhető"
  if [ "$AI_CHECK_WAKE" != "true" ]; then
    fail "AI szerver nem elérhető, ébresztés tiltva"
  fi
  log "-- AI szerver ébresztés kérése restic checkhez"
  api_post "/api/ai/node/wake" "{}" || log "-- AI wake API nem válaszolt, SSH várakozás folytatódik"
  deadline=$((SECONDS + AI_CHECK_WAIT_SECONDS))
  until "${SSH_BASE[@]}" "true" >/dev/null 2>&1; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      fail "AI szerver nem lett elérhető SSH-n ${AI_CHECK_WAIT_SECONDS} másodperc alatt"
    fi
    sleep 10
  done
  AI_WOKEN_BY_CHECK="true"
fi

if [ "$AI_WAS_ONLINE" = "true" ]; then
  log "-- AI szerver már elérhető volt, ellenőrzés után nem állítom le"
else
  log "-- AI szerver felébredt, ellenőrzés után leállítás kérhető"
fi

"${SSH_BASE[@]}" "test -d '${AI_BACKUP_MOUNT}/restic/homecontrol'" \
  || fail "Az AI restic repo könyvtár nem elérhető: ${AI_BACKUP_MOUNT}/restic/homecontrol"

restic "${RESTIC_ARGS[@]}" snapshots --tag homecontrol >/dev/null
restic "${RESTIC_ARGS[@]}" check

log "== Restic check kész =="
