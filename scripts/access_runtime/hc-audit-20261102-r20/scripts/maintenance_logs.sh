#!/usr/bin/env bash
set -Eeuo pipefail

BASE="/srv/docker/homecontrol"
TUYA_LOG_DIR="$BASE/apps/tuya-poller/logs"
Z2M_LOG_DIR="$BASE/infra/zigbee2mqtt/data/log"

TUYA_KEEP_DAYS=14
Z2M_KEEP_DAYS=14

if [ -d "$TUYA_LOG_DIR" ]; then
  find "$TUYA_LOG_DIR" -maxdepth 1 -type f \
    -name 'tuya_multi_connectors_*.log' -mtime +"$TUYA_KEEP_DAYS" -delete
fi

if [ -d "$Z2M_LOG_DIR" ]; then
  docker exec zigbee2mqtt find /app/data/log -type f \
    -mtime +"$Z2M_KEEP_DAYS" -delete
  docker exec zigbee2mqtt find /app/data/log -depth -type d \
    -empty -delete
fi
