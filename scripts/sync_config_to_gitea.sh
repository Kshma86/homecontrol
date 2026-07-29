#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
GITEA_REMOTE="${GITEA_REMOTE:-ssh://git@192.168.1.2:2222/homecontrol/config.git}"
GITEA_SSH_KEY="${GITEA_SSH_KEY:-$BASE/infra/ssh/ai_node_key}"
WORK_DIR="$(mktemp -d /tmp/hc-gitea-config.XXXXXX)"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

log() {
  echo "[$(date '+%F %T')] $*"
}

copy_path() {
  local source="$1"
  local target="$2"
  [ -e "$source" ] || return 0
  mkdir -p "$(dirname "$target")"
  if [ -d "$source" ]; then
    mkdir -p "$target"
    rsync -a --delete --delete-excluded \
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
    rsync -a "$source" "$target"
  fi
}

export GIT_SSH_COMMAND="ssh -i $GITEA_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

log "Config sync indul: $GITEA_REMOTE"
if ! git clone "$GITEA_REMOTE" "$WORK_DIR/repo" >/dev/null 2>&1; then
  mkdir -p "$WORK_DIR/repo"
  git -C "$WORK_DIR/repo" init
  git -C "$WORK_DIR/repo" remote add origin "$GITEA_REMOTE"
  git -C "$WORK_DIR/repo" checkout -b main
fi

REPO="$WORK_DIR/repo"
git -C "$REPO" config user.name "HomeControl Backup"
git -C "$REPO" config user.email "backup@homecontrol.local"

copy_path "$BASE/homeassistant/config" "$REPO/homeassistant/config"
copy_path "$BASE/homeassistant/docker-compose.yml" "$REPO/homeassistant/docker-compose.yml"
copy_path "$BASE/infra/docker-compose.yml" "$REPO/infra/docker-compose.yml"
copy_path "$BASE/scripts" "$REPO/scripts"
copy_path "$BASE/apps" "$REPO/apps"
copy_path "$BASE/docs/ai/backup-domain.md" "$REPO/docs/ai/backup-domain.md"

cat > "$REPO/.gitignore" <<'EOF'
.env
*.db
*.db-*
*.log
*.log.*
*.log.fault
*.tar.gz
__pycache__/
.cache/
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
tuya-poller/logs/
tuya-poller/multi_connector_config.json
xiaomi-x10/x10_maps/captures/
EOF

git -C "$REPO" add -A
if git -C "$REPO" diff --cached --quiet; then
  log "Nincs változás, push kihagyva"
  exit 0
fi

git -C "$REPO" commit -m "Update HomeControl configuration snapshot"
git -C "$REPO" push -u origin main
log "Config sync kész"
