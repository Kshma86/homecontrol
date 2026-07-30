#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
TARGET="${1:-}"

if [ -z "$TARGET" ]; then
  echo "Usage: $0 TARGET_DIR" >&2
  exit 2
fi

copy_path() {
  local source="$1"
  local target="$2"
  [ -e "$source" ] || return 0
  mkdir -p "$(dirname "$target")"
  if [ -d "$source" ]; then
    mkdir -p "$target"
    rsync -a --no-owner --no-group --delete --delete-excluded \
      --exclude '.git' \
      --exclude '.env' \
      --exclude '*.db' \
      --exclude '*.db-*' \
      --exclude '*.log' \
      --exclude '*.log.*' \
      --exclude '*.log.fault' \
      --exclude '*.tar.gz' \
      --exclude '__pycache__' \
      --exclude '.cache' \
      --exclude 'node_modules' \
      --exclude 'dist' \
      --exclude 'build' \
      --exclude '.ha_run.lock' \
      --exclude 'secrets.yaml' \
      --exclude '.storage' \
      --exclude 'deps' \
      --exclude 'tts' \
      --exclude 'postgres/data' \
      --exclude 'mqtt/data' \
      --exclude 'mqtt/log' \
      --exclude 'zigbee2mqtt/data/log' \
      --exclude 'tuya-poller/logs' \
      --exclude 'tuya-poller/multi_connector_config.json' \
      --exclude 'xiaomi-x10/x10_maps/captures' \
      --exclude 'infra/ssh' \
      "$source/" "$target/"
  else
    rsync -a --no-owner --no-group "$source" "$target"
  fi
}

mkdir -p "$TARGET"
copy_path "$BASE/homeassistant/config" "$TARGET/homeassistant/config"
copy_path "$BASE/homeassistant/docker-compose.yml" "$TARGET/homeassistant/docker-compose.yml"
copy_path "$BASE/infra/docker-compose.yml" "$TARGET/infra/docker-compose.yml"
copy_path "$BASE/infra/backend" "$TARGET/infra/backend"
copy_path "$BASE/infra/frontend" "$TARGET/infra/frontend"
copy_path "$BASE/scripts" "$TARGET/scripts"
copy_path "$BASE/apps" "$TARGET/apps"
copy_path "$BASE/secrets" "$TARGET/secrets"
copy_path "$BASE/docs/ai/backup-domain.md" "$TARGET/docs/ai/backup-domain.md"
copy_path "$BASE/docs/backup-restore-runbook.md" "$TARGET/docs/backup-restore-runbook.md"

cat > "$TARGET/.gitignore" <<'EOF'
.env
*.db
*.db-*
*.log
*.log.*
*.log.fault
*.tar.gz
__pycache__/
.cache/
node_modules/
dist/
build/
.ha_run.lock
secrets.yaml
.storage/
deps/
tts/
postgres/data/
mqtt/data/
mqtt/log/
zigbee2mqtt/data/log/
infra/ssh/
secrets/*
!secrets/.gitignore
!secrets/README.md
!secrets/manifest.txt
!secrets/age-recipient.txt
!secrets/*.age
!secrets/*.age.sha256
tuya-poller/logs/
tuya-poller/multi_connector_config.json
xiaomi-x10/x10_maps/captures/
EOF
