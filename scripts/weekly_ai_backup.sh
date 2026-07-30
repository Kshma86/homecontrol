#!/usr/bin/env bash
set -Eeuo pipefail

BASE="/srv/docker/homecontrol"
BACKUP_ROOT="${BACKUP_ROOT:-$BASE/backups}"
SETTINGS_FILE="$BACKUP_ROOT/backup_settings.json"
LOG_FILE="$BACKUP_ROOT/backup.log"
NOTIFY_SCRIPT="$BASE/scripts/notify_backup_result.sh"
AI_BACKUP_LOCK_FILE="$BACKUP_ROOT/ai-backup.lock"
AI_BACKUP_STATE_FILE="$BACKUP_ROOT/ai-backup-state.json"
AI_SHUTDOWN_REQUEST_FILE="$BACKUP_ROOT/ai-shutdown-after-backup.request"
LOCK_ACQUIRED=false

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

write_state() {
  local state="$1"
  local detail="${2:-}"
  mkdir -p "$BACKUP_ROOT"
  printf '{"state":"%s","updated_at":"%s","pid":%s,"detail":"%s"}\n' \
    "$state" "$(date -Iseconds)" "$$" "$(printf '%s' "$detail" | sed 's/\\/\\\\/g; s/"/\\"/g')" > "$AI_BACKUP_STATE_FILE"
}

deferred_shutdown_delay() {
  python3 - "$AI_SHUTDOWN_REQUEST_FILE" "$AI_BACKUP_POWER_OFF_DELAY_SECONDS" <<'PY' 2>/dev/null || printf '%s\n' "$AI_BACKUP_POWER_OFF_DELAY_SECONDS"
import json
import sys

path, default = sys.argv[1], sys.argv[2]
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    print(int(data.get("power_off_delay_sec") or default))
except Exception:
    print(default)
PY
}

run_shutdown_request() {
  local source="$1"
  local delay="${2:-$AI_BACKUP_POWER_OFF_DELAY_SECONDS}"
  log "-- AI szerver leállítás kérése (${source})"
  api_post "/api/ai/node/command" "{\"action\":\"shutdown\",\"schedule_power_off_on_failure\":true,\"power_off_delay_sec\":${delay},\"defer_if_backup_running\":false}" \
    || return 1
}

finish_deferred_shutdown() {
  local status="$1"
  if [ ! -f "$AI_SHUTDOWN_REQUEST_FILE" ]; then
    return 0
  fi
  if [ "$status" -ne 0 ]; then
    log "-- Halasztott AI shutdown kérés marad, mert a backup hibával állt le"
    return 0
  fi
  local delay
  delay="$(deferred_shutdown_delay)"
  if run_shutdown_request "halasztott kérés" "$delay"; then
    rm -f "$AI_SHUTDOWN_REQUEST_FILE"
    log "-- Halasztott AI shutdown kérés teljesítve"
  else
    log "-- Halasztott AI shutdown kérés sikertelen, kérés fájl megtartva"
  fi
}

finish() {
  local status=$?
  set +e
  if [ "$LOCK_ACQUIRED" = "true" ]; then
    if [ "$status" -eq 0 ]; then
      write_state "idle" "last run successful"
    else
      write_state "failed" "last run failed; see backup.log"
    fi
  fi
  if [ "$LOCK_ACQUIRED" = "true" ]; then
    finish_deferred_shutdown "$status"
  fi
  if [ -x "$NOTIFY_SCRIPT" ]; then
    if [ "$status" -eq 0 ]; then
      "$NOTIFY_SCRIPT" "HomeControl backup" "Weekly AI HDD backup sikeresen lefutott." || true
    else
      "$NOTIFY_SCRIPT" "HomeControl backup hiba" "Weekly AI HDD backup hibával állt le. Nézd meg: $LOG_FILE" || true
    fi
  fi
  exit "$status"
}
trap finish EXIT

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
AI_BACKUP_WAKE_RETRY_SECONDS="${AI_BACKUP_WAKE_RETRY_SECONDS:-60}"
AI_BACKUP_WAIT_LOG_SECONDS="${AI_BACKUP_WAIT_LOG_SECONDS:-30}"
AI_BACKUP_SHUTDOWN_AFTER="${AI_BACKUP_SHUTDOWN_AFTER:-true}"
AI_BACKUP_POWER_OFF_DELAY_SECONDS="${AI_BACKUP_POWER_OFF_DELAY_SECONDS:-300}"
AI_NODE_STACK_DIR="${AI_NODE_STACK_DIR:-~/homecontrol-ai-node}"
AI_WAS_REACHABLE=false

mkdir -p "$BACKUP_ROOT"
exec 8>"$AI_BACKUP_LOCK_FILE"
if ! flock -n 8; then
  log "-- Weekly AI HDD backup már fut, új kérés kihagyva"
  write_state "running" "another backup process owns the lock"
  exit 0
fi
LOCK_ACQUIRED=true
printf '%s\n' "$$" > "$AI_BACKUP_LOCK_FILE"
write_state "running" "weekly AI HDD backup running"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5)
if [ -n "$AI_BACKUP_SSH_KEY" ] && [ -f "$AI_BACKUP_SSH_KEY" ]; then
  SSH_OPTS=(-i "$AI_BACKUP_SSH_KEY" "${SSH_OPTS[@]}")
fi

ssh_ready() {
  ssh "${SSH_OPTS[@]}" "${AI_BACKUP_USER}@${AI_BACKUP_HOST}" "true" >/dev/null 2>&1
}

log "== Weekly AI HDD backup indul =="
if ssh_ready; then
  AI_WAS_REACHABLE=true
  log "-- AI szerver már elérhető volt induláskor, backup után nem állítom le automatikusan"
else
  log "-- AI szerver nem volt elérhető induláskor, ébresztés kérése"
  api_post "/api/ai/node/wake" "{}" || log "-- AI wake API nem válaszolt, SSH várakozás folytatódik"
fi

deadline=$((SECONDS + AI_BACKUP_WAIT_SECONDS))
next_wake_retry=$((SECONDS + AI_BACKUP_WAKE_RETRY_SECONDS))
next_wait_log=$((SECONDS + AI_BACKUP_WAIT_LOG_SECONDS))
until ssh_ready; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    log "HIBA: AI szerver nem lett elérhető SSH-n ${AI_BACKUP_WAIT_SECONDS} másodperc alatt"
    exit 1
  fi
  if [ "$SECONDS" -ge "$next_wait_log" ]; then
    remaining=$((deadline - SECONDS))
    log "-- AI szerver SSH még nem elérhető, várakozás folytatódik (${remaining}s maradt)"
    next_wait_log=$((SECONDS + AI_BACKUP_WAIT_LOG_SECONDS))
  fi
  if [ "$SECONDS" -ge "$next_wake_retry" ]; then
    log "-- AI wake ismétlés, mert SSH még nem elérhető"
    api_post "/api/ai/node/wake" "{}" || log "-- Ismételt AI wake API nem válaszolt"
    next_wake_retry=$((SECONDS + AI_BACKUP_WAKE_RETRY_SECONDS))
  fi
  sleep 10
done

log "-- AI szerver SSH elérhető, kötelező restic backup indul"
log "-- Encrypted secrets bundle frissítés indul"
if "$BASE/scripts/create_secrets_bundle.sh"; then
  log "-- Encrypted secrets bundle frissítés kész"
else
  log "-- Encrypted secrets bundle frissítés kihagyva vagy hibás; a full backup folytatódik"
fi

log "-- Gitea config snapshot sync indul"
"$BASE/scripts/sync_config_to_gitea.sh"
log "-- Gitea config snapshot sync kész"

log "-- AI szerver Gitea dump indul"
if ssh "${SSH_OPTS[@]}" "${AI_BACKUP_USER}@${AI_BACKUP_HOST}" "cd ${AI_NODE_STACK_DIR} && [ -x ./backup_gitea.sh ] && ./backup_gitea.sh"; then
  log "-- Gitea dump kész"
else
  log "-- Gitea dump nem futott le, a kötelező restic backup folytatódik"
fi

log "-- Kötelező restic backup indul"
RESTIC_REQUIRED=true "$BASE/scripts/backup_hc.sh"

if [ "$AI_BACKUP_SHUTDOWN_AFTER" = "true" ] && [ "$AI_WAS_REACHABLE" != "true" ]; then
  if run_shutdown_request "weekly auto" "$AI_BACKUP_POWER_OFF_DELAY_SECONDS"; then
    rm -f "$AI_SHUTDOWN_REQUEST_FILE"
  else
    log "-- AI shutdown API nem válaszolt"
  fi
elif [ "$AI_WAS_REACHABLE" = "true" ]; then
  log "-- AI szerver leállítás kihagyva: induláskor már be volt kapcsolva"
else
  log "-- AI szerver leállítás kihagyva"
fi

log "== Weekly AI HDD backup kész =="
