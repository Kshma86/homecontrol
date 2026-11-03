#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BASE="${HC_PROJECT_ROOT:-/srv/docker/homecontrol}"
export BASE
CODE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$CODE_DIR/deployment_policy_cli.py" --worker-mode weekly
: "${HC_BACKUP_RUN_ID:?Use backup_runner.py}"
state() { python3 "$CODE_DIR/backup_job_state.py" "$@"; }
BACKUP_ROOT="${BACKUP_ROOT:-$BASE/backups}"
SETTINGS_FILE="${HC_BACKUP_SETTINGS_FILE:?Use backup_runner.py}"
LOG_FILE="$BACKUP_ROOT/backup.log"
NOTIFY_SCRIPT="$BASE/scripts/notify_backup_result.sh"
AI_BACKUP_LOCK_FILE="$BACKUP_ROOT/ai-backup.lock"
AI_BACKUP_STATE_FILE="$BACKUP_ROOT/ai-backup-state.json"
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

# Router storage has no dependency on AI power, SSH, Gitea or its dump.
# This branch runs before installing legacy AI shutdown callbacks.
if [ "$(setting backup_target ai_sftp)" = router_ftp ]; then
  status=0
  state target gitea_origin skipped "Router mode: AI Gitea is disabled"
  state target gitea_dump skipped "Router mode: no AI Gitea dump"
  state target secrets_bundle running
  if python3 "$CODE_DIR/export_config_snapshot.py" --secrets-manifest "$HC_BACKUP_WORK_DIR/secrets-manifest.txt" \
    && SECRETS_MANIFEST="$HC_BACKUP_WORK_DIR/secrets-manifest.txt" "$CODE_DIR/create_secrets_bundle.sh"; then
    state target secrets_bundle succeeded
  else
    state target secrets_bundle failed "Router recovery secrets refresh failed"
    status=1
  fi
  if [ "$(setting git_enabled true)" = true ]; then
    if bash "$CODE_DIR/backup_offsite_worker.sh"; then :; else status=1; fi
  else
    state target git_offsite skipped "Git disabled"
  fi
  if RESTIC_REQUIRED=true bash "$CODE_DIR/backup_archive_worker.sh"; then :; else status=1; fi
  exit "$status"
fi

log() {
  mkdir -p "$BACKUP_ROOT"
  echo "[$(date '+%F %T')] $*"
}

write_state() {
  state ai-state "$1" "${2:-}"
}

run_shutdown_request() {
  local source="$1"
  local delay="${2:-$AI_BACKUP_POWER_OFF_DELAY_SECONDS}"
  log "-- AI szerver leállítás kérése (${source})"
  api_post "/api/ai/node/command" "{\"action\":\"shutdown\",\"schedule_power_off_on_failure\":true,\"power_off_delay_sec\":${delay},\"backup_run_id\":\"${HC_BACKUP_RUN_ID}\"}" \
    || return 1
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
    if [ "${AI_BACKUP_SHUTDOWN_AFTER:-false}" = "true" ] \
      && [ "${AI_WAS_REACHABLE:-true}" != "true" ]; then
      run_shutdown_request "weekly auto, backup status=${status}" "${AI_BACKUP_POWER_OFF_DELAY_SECONDS:-300}" \
        || log "-- AI shutdown API nem válaszolt"
    fi
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
    docker exec -i "${HC_BACKEND_CONTAINER:-homecontrol-backend}" python - "$path" "$body" <<'PY'
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
AI_BACKUP_SHUTDOWN_AFTER="${AI_BACKUP_SHUTDOWN_AFTER:-$(setting ai_weekly_shutdown_after true)}"
AI_BACKUP_POWER_OFF_DELAY_SECONDS="${AI_BACKUP_POWER_OFF_DELAY_SECONDS:-300}"
AI_NODE_STACK_DIR="${AI_NODE_STACK_DIR:-~/homecontrol-ai-node}"
AI_WAS_REACHABLE=false

mkdir -p "$BACKUP_ROOT"
LOCK_ACQUIRED=true
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
  log "-- AI szerver már elérhető volt induláskor"
else
  log "-- AI szerver nem volt elérhető induláskor, ébresztés kérése"
  api_post "/api/ai/node/wake" "{\"backup_run_id\":\"${HC_BACKUP_RUN_ID}\"}" || log "-- AI wake API nem válaszolt, SSH várakozás folytatódik"
fi

deadline=$((SECONDS + AI_BACKUP_WAIT_SECONDS))
next_wake_retry=$((SECONDS + AI_BACKUP_WAKE_RETRY_SECONDS))
next_wait_log=$((SECONDS + AI_BACKUP_WAIT_LOG_SECONDS))
until ssh_ready; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    log "HIBA: AI szerver nem lett elérhető SSH-n ${AI_BACKUP_WAIT_SECONDS} másodperc alatt"
    break
  fi
  if [ "$SECONDS" -ge "$next_wait_log" ]; then
    remaining=$((deadline - SECONDS))
    log "-- AI szerver SSH még nem elérhető, várakozás folytatódik (${remaining}s maradt)"
    next_wait_log=$((SECONDS + AI_BACKUP_WAIT_LOG_SECONDS))
  fi
  if [ "$SECONDS" -ge "$next_wake_retry" ]; then
    log "-- AI wake ismétlés, mert SSH még nem elérhető"
    api_post "/api/ai/node/wake" "{\"backup_run_id\":\"${HC_BACKUP_RUN_ID}\"}" || log "-- Ismételt AI wake API nem válaszolt"
    next_wake_retry=$((SECONDS + AI_BACKUP_WAKE_RETRY_SECONDS))
  fi
  sleep 10
done

log "-- AI szerver SSH elérhető, kötelező restic backup indul"
status=0
state target secrets_bundle running
log "-- Encrypted secrets bundle frissítés indul"
if python3 "$BASE/scripts/export_config_snapshot.py" --secrets-manifest "$HC_BACKUP_WORK_DIR/secrets-manifest.txt" \
  && SECRETS_MANIFEST="$HC_BACKUP_WORK_DIR/secrets-manifest.txt" "$BASE/scripts/create_secrets_bundle.sh"; then
  state target secrets_bundle succeeded
else
  state target secrets_bundle failed "Secrets bundle refresh failed (optional; existing bundle retained)"
fi

if [ "$(setting git_enabled true)" = true ]; then
  if bash "$CODE_DIR/backup_config_sync_worker.sh"; then :; else status=1; fi
else
  state target gitea_origin skipped "Git disabled"
  state target git_offsite skipped "Git disabled"
fi

state target gitea_dump running
if ssh "${SSH_OPTS[@]}" "${AI_BACKUP_USER}@${AI_BACKUP_HOST}" "cd ${AI_NODE_STACK_DIR} && [ -x ./backup_gitea.sh ] && ./backup_gitea.sh"; then
  state target gitea_dump succeeded
  log "-- Gitea dump kész"
else
  state target gitea_dump failed "Gitea dump failed"
  log "-- Gitea dump nem futott le, a kötelező restic backup folytatódik"
  status=1
fi

log "-- Kötelező helyi és restic backup indul"
if RESTIC_REQUIRED=true bash "$CODE_DIR/backup_archive_worker.sh"; then :; else status=1; fi
if [ "$status" -eq 0 ]; then
  log "== Weekly AI HDD backup kész =="
else
  log "HIBA: Weekly backup egyik kötelező célja hibás; lásd a célonkénti állapotot"
fi
exit "$status"
