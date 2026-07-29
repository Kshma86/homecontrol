#!/usr/bin/env bash
set -Eeuo pipefail

# =========================================================
# HomeControl backup script
# =========================================================

# ---------- Alap beállítások ----------

# Ha az előző sorban véletlen idézőjel hiba lenne nálad másoláskor, használd ezt:
TS="$(date +%F_%H-%M-%S)"

BASE="/srv/docker/homecontrol"
BACKUP_ROOT="${BACKUP_ROOT:-$BASE/backups}"
SETTINGS_FILE="$BACKUP_ROOT/backup_settings.json"
TMP_ROOT="/tmp/hc_backup"
WORK_DIR="$TMP_ROOT/$TS"
BACKUP_DIR="$WORK_DIR/homecontrol_$TS"
ARCHIVE="$BACKUP_ROOT/homecontrol_$TS.tar.gz"
LOG_FILE="$BACKUP_ROOT/backup.log"
LOCK_FILE="/tmp/homecontrol_backup.lock"

POSTGRES_CONTAINER="homecontrol-postgres"
POSTGRES_USER="homecontrol"
POSTGRES_DB="homecontrol"

HC_APPS="$BASE/apps"
INFRA_DIR="$BASE/infra"
Z2M_DATA_DIR="$BASE/infra/zigbee2mqtt/data"

# opcionális extra utak
SCRIPTS_DIR="$BASE/scripts"
HOMEASSISTANT_DIR="$BASE/homeassistant"

# retention
KEEP_DAYS=14

# opcionális offsite/dev gép sync
ENABLE_RSYNC="false"
RSYNC_TARGET="a@devpc:/home/a/hc_backups/"

# ---------- Függvények ----------
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

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

fail() {
  log "HIBA: $*"
  exit 1
}

restic_unavailable() {
  local message="$1"
  if [ "${RESTIC_REQUIRED:-false}" = "true" ]; then
    fail "$message"
  fi
  log "-- Restic snapshot kihagyva: $message"
  log "== Backup kész restic nélkül: $ARCHIVE =="
  exit 0
}

# ---------- Könyvtárak ----------
mkdir -p "$BACKUP_ROOT"
mkdir -p "$WORK_DIR"
mkdir -p "$BACKUP_DIR"

INCLUDE_POSTGRES="$(setting include_postgres true)"
INCLUDE_APPS="$(setting include_apps true)"
INCLUDE_INFRA="$(setting include_infra true)"
INCLUDE_ZIGBEE2MQTT="$(setting include_zigbee2mqtt true)"
INCLUDE_HOMEASSISTANT="$(setting include_homeassistant true)"
INCLUDE_SCRIPTS="$(setting include_scripts true)"
INCLUDE_DOCKER_META="$(setting include_docker_meta true)"
INCLUDE_DOCKER_VOLUMES="$(setting include_docker_volumes true)"
INCLUDE_MEDIA="$(setting include_media true)"
INCLUDE_GITEA="$(setting include_gitea true)"
RESTIC_ENABLED="$(setting restic_enabled false)"
AI_BACKUP_HOST="$(setting ai_backup_host 192.168.1.2)"
AI_BACKUP_USER="$(setting ai_backup_user a)"
AI_BACKUP_MOUNT="$(setting ai_backup_mount /mnt/hc-backup)"
AI_BACKUP_SSH_KEY="$(setting ai_backup_ssh_key /srv/docker/homecontrol/infra/ssh/ai_node_key)"
RESTIC_REPOSITORY="$(setting restic_repository sftp:${AI_BACKUP_USER}@${AI_BACKUP_HOST}:${AI_BACKUP_MOUNT}/restic/homecontrol)"
RESTIC_PASSWORD_FILE="$(setting restic_password_file /etc/homecontrol/restic-password)"
RESTIC_KEEP_DAILY="$(setting restic_keep_daily 14)"
RESTIC_KEEP_WEEKLY="$(setting restic_keep_weekly 8)"
RESTIC_KEEP_MONTHLY="$(setting restic_keep_monthly 6)"
RESTIC_REQUIRED="${RESTIC_REQUIRED:-$(setting restic_required false)}"
KEEP_DAYS="$(setting retention_days "$KEEP_DAYS")"

exec 9>"$LOCK_FILE"
flock -n 9 || fail "Már fut egy másik HomeControl backup"

log "== HomeControl backup indul: $TS =="

# ---------- Ellenőrzések ----------
[ -d "$BASE" ] || fail "Nincs ilyen BASE könyvtár: $BASE"
[ -d "$HC_APPS" ] || fail "Nincs ilyen apps könyvtár: $HC_APPS"
[ -d "$INFRA_DIR" ] || fail "Nincs ilyen infra könyvtár: $INFRA_DIR"
[ -d "$Z2M_DATA_DIR" ] || fail "Nincs ilyen Zigbee2MQTT data könyvtár: $Z2M_DATA_DIR"

docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 || fail "Nincs ilyen konténer: $POSTGRES_CONTAINER"

# ---------- 1) PostgreSQL dump ----------
if [ "$INCLUDE_POSTGRES" = "true" ]; then
  log "-- PostgreSQL dump"
  mkdir -p "$BACKUP_DIR/postgres"

  DUMP_IN_CONTAINER="/tmp/${POSTGRES_DB}_${TS}.dump"
  DUMP_ON_HOST="$BACKUP_DIR/postgres/${POSTGRES_DB}_${TS}.dump"

  docker exec "$POSTGRES_CONTAINER" pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -Fc \
    -f "$DUMP_IN_CONTAINER"

  docker cp "$POSTGRES_CONTAINER:$DUMP_IN_CONTAINER" "$DUMP_ON_HOST"
  docker exec "$POSTGRES_CONTAINER" rm -f "$DUMP_IN_CONTAINER"

  [ -f "$DUMP_ON_HOST" ] || fail "A PostgreSQL dump nem jött létre"
else
  log "-- PostgreSQL dump kihagyva"
fi

# ---------- 2) Apps mentés ----------
if [ "$INCLUDE_APPS" = "true" ]; then
  log "-- Apps mentés"
  mkdir -p "$BACKUP_DIR/apps"

  rsync -a \
    --exclude 'tuya-poller/logs' \
    --exclude 'tuya-poller/logs/*' \
    "$HC_APPS/" "$BACKUP_DIR/apps/"
else
  log "-- Apps mentés kihagyva"
fi

# ---------- 3) Infra mentés ----------
if [ "$INCLUDE_INFRA" = "true" ]; then
  log "-- Infra mentés"
  mkdir -p "$BACKUP_DIR/infra"

  # Nem akarjuk a runtime postgres adatkönyvtárat vakon menteni,
  # mert futó DB mellett az nem konzisztens restore-forrás.
  # A pg_dump a hivatalos restore alap.
  rsync -a \
    --exclude 'postgres/data' \
    --exclude 'postgres/data/*' \
    --exclude 'mqtt/data' \
    --exclude 'mqtt/data/*' \
    --exclude 'mqtt/log' \
    --exclude 'mqtt/log/*' \
    --exclude 'zigbee2mqtt/data' \
    --exclude 'zigbee2mqtt/data/*' \
    "$INFRA_DIR/" "$BACKUP_DIR/infra/"
else
  log "-- Infra mentés kihagyva"
fi

# ---------- 4) Zigbee2MQTT data külön mentés ----------
if [ "$INCLUDE_ZIGBEE2MQTT" = "true" ]; then
  log "-- Zigbee2MQTT data külön mentés"
  mkdir -p "$BACKUP_DIR/zigbee2mqtt"
  rsync -a \
    --exclude 'log' \
    --exclude 'log/*' \
    "$Z2M_DATA_DIR/" "$BACKUP_DIR/zigbee2mqtt/data/"
else
  log "-- Zigbee2MQTT data mentés kihagyva"
fi

# ---------- 5) Opcionális extra könyvtárak ----------
if [ "$INCLUDE_SCRIPTS" = "true" ] && [ -d "$SCRIPTS_DIR" ]; then
  log "-- Scripts mentés"
  cp -a "$SCRIPTS_DIR" "$BACKUP_DIR/"
else
  log "-- Scripts mentés kihagyva"
fi

if [ "$INCLUDE_HOMEASSISTANT" = "true" ] && [ -d "$HOMEASSISTANT_DIR" ]; then
  log "-- Home Assistant mappa mentés"
  cp -a "$HOMEASSISTANT_DIR" "$BACKUP_DIR/"
else
  log "-- Home Assistant mentés kihagyva"
fi

# ---------- 6) Docker meta ----------
if [ "$INCLUDE_DOCKER_META" = "true" ]; then
  log "-- Docker meta mentés"
  docker ps -a > "$BACKUP_DIR/docker_ps_a.txt"
  docker images > "$BACKUP_DIR/docker_images.txt"
  docker volume ls > "$BACKUP_DIR/docker_volume_ls.txt"
  docker network ls > "$BACKUP_DIR/docker_network_ls.txt"
  docker inspect "$POSTGRES_CONTAINER" > "$BACKUP_DIR/postgres_container_inspect.json" || true

  # ha ezek futnak, hasznos lehet:
  docker inspect homecontrol-zigbee2mqtt > "$BACKUP_DIR/zigbee2mqtt_container_inspect.json" 2>/dev/null || true
  docker inspect homecontrol-mosquitto > "$BACKUP_DIR/mosquitto_container_inspect.json" 2>/dev/null || true
  docker inspect hc_ingest > "$BACKUP_DIR/hc_ingest_container_inspect.json" 2>/dev/null || true
  docker inspect homecontrol-tuya-poller > "$BACKUP_DIR/tuya_poller_container_inspect.json" 2>/dev/null || true
else
  log "-- Docker meta mentés kihagyva"
fi

# ---------- 7) Host meta ----------
log "-- Host meta mentés"
uname -a > "$BACKUP_DIR/uname.txt" || true
hostnamectl > "$BACKUP_DIR/hostnamectl.txt" 2>/dev/null || true
docker version > "$BACKUP_DIR/docker_version.txt" 2>/dev/null || true
docker info > "$BACKUP_DIR/docker_info.txt" 2>/dev/null || true
df -h > "$BACKUP_DIR/df_h.txt" || true
mount > "$BACKUP_DIR/mount.txt" || true
crontab -l > "$BACKUP_DIR/crontab.txt" 2>/dev/null || true

# ---------- 8) Manifest + checksum ----------
log "-- Manifest és checksum készítés"
(
  cd "$BACKUP_DIR"
  find . -type f | sort > MANIFEST.txt
  find . -type f ! -name 'SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt
)

# ---------- 9) Tömörítés ----------
log "-- Tömörítés"
tar -C "$WORK_DIR" -czf "$ARCHIVE" "$(basename "$BACKUP_DIR")"

[ -f "$ARCHIVE" ] || fail "Nem jött létre az archívum: $ARCHIVE"

# ---------- 10) Archívum ellenőrzés ----------
log "-- Archívum ellenőrzés"
tar -tzf "$ARCHIVE" >/dev/null

# ---------- 11) Opcionális rsync másik gépre ----------
if [ "$ENABLE_RSYNC" = "true" ]; then
  log "-- Rsync indul: $RSYNC_TARGET"
  rsync -avh --progress "$ARCHIVE" "$RSYNC_TARGET"
fi

# ---------- 12) Retention ----------
log "-- Régi mentések törlése (${KEEP_DAYS} napnál régebbiek)"
find "$BACKUP_ROOT" -maxdepth 1 -type f -name "homecontrol_*.tar.gz" -mtime +"$KEEP_DAYS" -delete

# ---------- 13) Restic snapshot az AI szerver HDD-re ----------
if [ "$RESTIC_ENABLED" = "true" ]; then
  log "-- Restic snapshot ellenőrzés"
  command -v restic >/dev/null 2>&1 || restic_unavailable "A restic nincs telepítve"
  command -v ssh >/dev/null 2>&1 || restic_unavailable "Az ssh kliens nincs telepítve"
  [ -n "$RESTIC_REPOSITORY" ] || restic_unavailable "Nincs restic_repository beállítva"
  [ -f "$RESTIC_PASSWORD_FILE" ] || restic_unavailable "Nincs restic password file: $RESTIC_PASSWORD_FILE"

  export RESTIC_REPOSITORY
  export RESTIC_PASSWORD_FILE
  export RESTIC_CACHE_DIR="$TMP_ROOT/restic-cache"
  mkdir -p "$RESTIC_CACHE_DIR"
  RESTIC_ARGS=()
  if [ -n "$AI_BACKUP_SSH_KEY" ] && [ -f "$AI_BACKUP_SSH_KEY" ]; then
    RESTIC_ARGS=(-o "sftp.command=ssh -i $AI_BACKUP_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new ${AI_BACKUP_USER}@${AI_BACKUP_HOST} -s sftp")
    SSH_BASE=(ssh -i "$AI_BACKUP_SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${AI_BACKUP_USER}@${AI_BACKUP_HOST}")
  else
    RESTIC_ARGS=(-o "sftp.command=ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new ${AI_BACKUP_USER}@${AI_BACKUP_HOST} -s sftp")
    SSH_BASE=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${AI_BACKUP_USER}@${AI_BACKUP_HOST}")
  fi

  log "-- AI backup HDD ellenőrzés: ${AI_BACKUP_USER}@${AI_BACKUP_HOST}:${AI_BACKUP_MOUNT}"
  "${SSH_BASE[@]}" "test -w '${AI_BACKUP_MOUNT}' && mkdir -p '${AI_BACKUP_MOUNT}/restic/homecontrol' '${AI_BACKUP_MOUNT}/database' '${AI_BACKUP_MOUNT}/config' '${AI_BACKUP_MOUNT}/files'" \
    || restic_unavailable "Az AI backup HDD nem írható vagy nem elérhető: ${AI_BACKUP_MOUNT}"

  RESTIC_SOURCES=("$ARCHIVE")
  [ -d "$HC_APPS" ] && RESTIC_SOURCES+=("$HC_APPS")
  [ -d "$INFRA_DIR" ] && RESTIC_SOURCES+=("$INFRA_DIR")
  [ -d "$HOMEASSISTANT_DIR" ] && RESTIC_SOURCES+=("$HOMEASSISTANT_DIR")
  [ -d "$SCRIPTS_DIR" ] && RESTIC_SOURCES+=("$SCRIPTS_DIR")
  if [ "$INCLUDE_DOCKER_VOLUMES" = "true" ] && [ -d /var/lib/docker/volumes ]; then
    RESTIC_SOURCES+=("/var/lib/docker/volumes")
  fi
  if [ "$INCLUDE_MEDIA" = "true" ] && [ -d "$BASE/media" ]; then
    RESTIC_SOURCES+=("$BASE/media")
  fi
  if [ "$INCLUDE_GITEA" = "true" ] && [ -d /srv/gitea ]; then
    RESTIC_SOURCES+=("/srv/gitea")
  fi

  if ! restic "${RESTIC_ARGS[@]}" snapshots >/dev/null 2>&1; then
    log "-- Restic repo inicializálás: $RESTIC_REPOSITORY"
    restic "${RESTIC_ARGS[@]}" init
  fi

  log "-- Restic backup: ${RESTIC_SOURCES[*]}"
  restic "${RESTIC_ARGS[@]}" backup "${RESTIC_SOURCES[@]}" \
    --tag homecontrol \
    --tag ai-hdd \
    --exclude "$BASE/infra/postgres/data" \
    --exclude "$BASE/infra/mqtt/data" \
    --exclude "$BASE/infra/mqtt/log" \
    --exclude "$BASE/infra/zigbee2mqtt/data/log" \
    --exclude "$BASE/apps/tuya-poller/logs" \
    --exclude "$BASE/**/__pycache__"

  log "-- Restic retention: daily=$RESTIC_KEEP_DAILY weekly=$RESTIC_KEEP_WEEKLY monthly=$RESTIC_KEEP_MONTHLY"
  restic "${RESTIC_ARGS[@]}" forget \
    --tag homecontrol \
    --keep-daily "$RESTIC_KEEP_DAILY" \
    --keep-weekly "$RESTIC_KEEP_WEEKLY" \
    --keep-monthly "$RESTIC_KEEP_MONTHLY" \
    --prune
else
  log "-- Restic snapshot kihagyva"
fi

# ---------- 14) Kész ----------
ARCHIVE_SIZE="$(du -h "$ARCHIVE" | awk '{print $1}')"
log "== Backup kész: $ARCHIVE (${ARCHIVE_SIZE}) =="
