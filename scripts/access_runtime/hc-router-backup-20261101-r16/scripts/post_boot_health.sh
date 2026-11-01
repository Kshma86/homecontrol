#!/usr/bin/env bash
set -Eeuo pipefail

BASE="/srv/docker/homecontrol"
INFRA="$BASE/infra"
STATE_DIR="${HC_BOOT_HEALTH_STATE_DIR:-/run/homecontrol-post-boot-health}"
GROWATT_FAILURE_FILE="$STATE_DIR/growatt-unavailable"
COORDINATOR_HOST="${ZIGBEE_COORDINATOR_HOST:-192.168.1.59}"
COORDINATOR_PORT="${ZIGBEE_COORDINATOR_PORT:-6638}"
GROWATT_ENTITY="${HC_GROWATT_HEALTH_ENTITY:-sensor.pyl0chj016_output_power}"

mkdir -p "$STATE_DIR"

log() {
  printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
}

container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" = "true" ]
}

restart_container() {
  log "restarting container: $1"
  docker restart "$1" >/dev/null
}

coordinator_reachable() {
  timeout 5 bash -c "exec 3<>/dev/tcp/$COORDINATOR_HOST/$COORDINATOR_PORT" 2>/dev/null
}

zigbee_bridge_online() {
  local payload
  payload="$(docker exec homecontrol-mqtt mosquitto_sub \
    -h 127.0.0.1 -t zigbee/bridge/state -C 1 -W 4 2>/dev/null || true)"
  [[ "$payload" == *'online'* ]]
}

growatt_available() {
  docker exec -e HC_HEALTH_ENTITY="$GROWATT_ENTITY" homecontrol-ha-growatt-poller python -c '
import os
import requests

base = os.environ["HA_BASE_URL"].rstrip("/")
token = os.environ.get("HA_TOKEN", "")
entity = os.environ["HC_HEALTH_ENTITY"]
response = requests.get(
    f"{base}/api/states/{entity}",
    headers={"Authorization": f"Bearer {token}"},
    timeout=10,
)
if response.status_code != 200:
    raise SystemExit(1)
state = str(response.json().get("state", "")).strip().lower()
raise SystemExit(1 if state in {"", "unknown", "unavailable", "none"} else 0)
' >/dev/null 2>&1
}

report_stale_zigbee() {
  local active_ids row ext_id
  active_ids="$(docker exec homecontrol-postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select ext_id from hc.device where platform='"'"'zigbee'"'"' and is_active=true"' \
    2>/dev/null || true)"

  while IFS= read -r row; do
    ext_id="${row%%|*}"
    if grep -Fqx "$ext_id" <<<"$active_ids"; then
      printf '%s\n' "$row"
    fi
  done < <(docker exec zigbee2mqtt node -e '
const fs = require("fs");
const cutoff = Date.now() - 6 * 60 * 60 * 1000;
const rows = fs.readFileSync("/app/data/database.db", "utf8")
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line))
  .filter((row) => row.type === "EndDevice" && (!row.lastSeen || row.lastSeen < cutoff))
  .sort((a, b) => (a.lastSeen || 0) - (b.lastSeen || 0));
for (const row of rows) {
  const latest = row.lastSeen ? new Date(row.lastSeen).toISOString() : "never";
  console.log(`${row.ieeeAddr}|${row.modelId || "unknown"}|radio|${latest}`);
}
' 2>/dev/null || true)
}

log "post-boot health check started"

if coordinator_reachable; then
  if ! container_running zigbee2mqtt || ! zigbee_bridge_online; then
    restart_container zigbee2mqtt
    sleep 15
    if zigbee_bridge_online; then
      log "Zigbee2MQTT recovered"
    else
      log "WARNING: Zigbee2MQTT is still offline"
    fi
  else
    log "Zigbee coordinator and bridge are online"
  fi
else
  log "WARNING: Zigbee coordinator is unreachable at $COORDINATOR_HOST:$COORDINATOR_PORT"
fi

if container_running homeassistant && container_running homecontrol-ha-growatt-poller; then
  if growatt_available; then
    rm -f "$GROWATT_FAILURE_FILE"
    log "Home Assistant Growatt entity is available"
  elif [ -f "$GROWATT_FAILURE_FILE" ]; then
    log "Growatt is unavailable for a second consecutive check"
    restart_container homeassistant
    rm -f "$GROWATT_FAILURE_FILE"
  else
    date --iso-8601=seconds >"$GROWATT_FAILURE_FILE"
    log "WARNING: Growatt is unavailable; confirmation required on next check"
  fi
else
  log "WARNING: Home Assistant or Growatt poller container is not running"
fi

stale_rows="$(report_stale_zigbee)"
if [ -n "$stale_rows" ]; then
  while IFS='|' read -r ext_id name location latest; do
    log "WARNING: stale Zigbee device: $name ($ext_id), location=$location, latest=$latest"
  done <<<"$stale_rows"
else
  log "No Zigbee device has stale state data"
fi

log "post-boot health check finished"
