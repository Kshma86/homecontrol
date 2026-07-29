#!/usr/bin/env bash
set -Eeuo pipefail

BASE="/srv/docker/homecontrol"
BACKUP_ROOT="${BACKUP_ROOT:-$BASE/backups}"
SETTINGS_FILE="$BACKUP_ROOT/backup_settings.json"
LOG_FILE="$BACKUP_ROOT/backup.log"

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
  echo "[$(date '+%F %T')] $*" | tee -a "$LOG_FILE"
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

AI_BACKUP_HOST="$(setting ai_backup_host 192.168.1.2)"
AI_BACKUP_USER="$(setting ai_backup_user a)"
AI_BACKUP_SSH_KEY="$(setting ai_backup_ssh_key /srv/docker/homecontrol/infra/ssh/ai_node_key)"
AI_BACKUP_WAIT_SECONDS="${AI_BACKUP_WAIT_SECONDS:-900}"
AI_BACKUP_SHUTDOWN_AFTER="${AI_BACKUP_SHUTDOWN_AFTER:-true}"
AI_BACKUP_POWER_OFF_DELAY_SECONDS="${AI_BACKUP_POWER_OFF_DELAY_SECONDS:-300}"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5)
if [ -n "$AI_BACKUP_SSH_KEY" ] && [ -f "$AI_BACKUP_SSH_KEY" ]; then
  SSH_OPTS=(-i "$AI_BACKUP_SSH_KEY" "${SSH_OPTS[@]}")
fi

log "== Weekly AI HDD backup indul =="
log "-- AI szerver ébresztés kérése"
api_post "/api/ai/node/wake" "{}" || log "-- AI wake API nem válaszolt, SSH várakozás folytatódik"

deadline=$((SECONDS + AI_BACKUP_WAIT_SECONDS))
until ssh "${SSH_OPTS[@]}" "${AI_BACKUP_USER}@${AI_BACKUP_HOST}" "true" >/dev/null 2>&1; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    log "HIBA: AI szerver nem lett elérhető SSH-n ${AI_BACKUP_WAIT_SECONDS} másodperc alatt"
    exit 1
  fi
  sleep 10
done

log "-- AI szerver SSH elérhető, kötelező restic backup indul"
RESTIC_REQUIRED=true "$BASE/scripts/backup_hc.sh"

if [ "$AI_BACKUP_SHUTDOWN_AFTER" = "true" ]; then
  log "-- AI szerver leállítás kérése"
  api_post "/api/ai/node/command" "{\"action\":\"shutdown\",\"schedule_power_off_on_failure\":true,\"power_off_delay_sec\":${AI_BACKUP_POWER_OFF_DELAY_SECONDS}}" \
    || log "-- AI shutdown API nem válaszolt"
else
  log "-- AI szerver leállítás kihagyva"
fi

log "== Weekly AI HDD backup kész =="
