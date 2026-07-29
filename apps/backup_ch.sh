#!/usr/bin/env bash
set -euo pipefail

# ===== Beállítások =====
TS="$(date +%F_%H-%M-%S)"
BASE="/srv/docker/homecontrol"
BACKUP_DIR="$BASE/backups/daily/$TS"
TMP_DIR="/tmp/hc_backup_$TS"

POSTGRES_CONTAINER="homecontrol-postgres"
POSTGRES_USER="homecontrol"
POSTGRES_DB="homecontrol"

Z2M_DATA_DIR="$BASE/infra/zigbee2mqtt/data"
COMPOSE_DIR="$BASE/infra"

HC_APPS="$BASE/apps"

mkdir -p "$BACKUP_DIR"
mkdir -p "$TMP_DIR"

echo "== HomeControl backup indul: $TS =="

# ===== 1) Compose + config mentés =====
echo "-- Compose és config mentés"
mkdir -p "$BACKUP_DIR/config"
cp -a "$COMPOSE_DIR" "$BACKUP_DIR/config/"

# ===== 2) Zigbee2MQTT data mentés =====
echo "-- Zigbee2MQTT data mentés"
mkdir -p "$BACKUP_DIR/zigbee2mqtt"
cp -a "$Z2M_DATA_DIR" "$BACKUP_DIR/zigbee2mqtt/"

# ===== 3) Apps mentés =====
echo "-- Apps data mentés"
mkdir -p "$BACKUP_DIR/apps"
cp -a "$HC_APPS/tuya-poller" "$BACKUP_DIR/apps/"
echo "-- Ingest data mentés"
cp -a "$HC_APPS/hc_ingest" "$BACKUP_DIR/apps/"

# ===== 4) Home Assistant config mentés =====
echo "-- Home Assistant config mentés"
cp -a "$BASE/homeassistant" "$BACKUP_DIR/" 2>/dev/null || true

# ===== 5) PostgreSQL logikai dump =====
echo "-- PostgreSQL dump"
mkdir -p "$BACKUP_DIR/postgres"
docker exec "$POSTGRES_CONTAINER" pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -Fc \
  -f "/tmp/${POSTGRES_DB}_${TS}.dump"

docker cp \
  "$POSTGRES_CONTAINER:/tmp/${POSTGRES_DB}_${TS}.dump" \
  "$BACKUP_DIR/postgres/${POSTGRES_DB}_${TS}.dump"

docker exec "$POSTGRES_CONTAINER" rm -f "/tmp/${POSTGRES_DB}_${TS}.dump"

# ===== 6) Konténerlista + image lista =====
echo "-- Docker meta mentés"
docker ps -a > "$BACKUP_DIR/docker_ps_a.txt"
docker images > "$BACKUP_DIR/docker_images.txt"
docker volume ls > "$BACKUP_DIR/docker_volume_ls.txt"
docker network ls > "$BACKUP_DIR/docker_network_ls.txt"

# ===== 7) Teljes backup tömörítés =====
echo "-- Tömörítés"
tar -C "$(dirname "$BACKUP_DIR")" -czf "${BACKUP_DIR}.tar.gz" "$(basename "$BACKUP_DIR")"

# opcionális: kicsomagolt példány törlése, hogy csak a tar.gz maradjon
rm -rf "$BACKUP_DIR"

# ===== 8) Retention: 14 napnál régebbi daily mentések törlése =====
echo "-- Régi mentések törlése"
find "$BASE/backups/daily" -maxdepth 1 -type f -name "*.tar.gz" -mtime +14 -delete

echo "== Backup kész: ${BACKUP_DIR}.tar.gz =="
