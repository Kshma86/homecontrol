#!/usr/bin/env bash
set -Eeuo pipefail

GITEA_CONTAINER="${GITEA_CONTAINER:-homecontrol-ai-gitea}"
GITEA_DATA_DIR="${GITEA_DATA_DIR:-/mnt/hc-backup/gitea}"
GITEA_DUMP_DIR="${GITEA_DUMP_DIR:-/mnt/hc-backup/gitea-dumps}"
GITEA_DUMP_KEEP="${GITEA_DUMP_KEEP:-12}"
TS="$(date +%F_%H-%M-%S)"
DUMP_NAME="gitea_${TS}.zip"

log() {
  echo "[$(date '+%F %T')] $*"
}

fail() {
  log "HIBA: $*"
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "Docker nem elérhető"
docker inspect "$GITEA_CONTAINER" >/dev/null 2>&1 || fail "Nincs ilyen Gitea konténer: $GITEA_CONTAINER"
mkdir -p "$GITEA_DUMP_DIR"

log "Gitea dump indul: $DUMP_NAME"
docker exec -u git "$GITEA_CONTAINER" gitea dump \
  --config /data/gitea/conf/app.ini \
  --file "/tmp/$DUMP_NAME"
docker cp "$GITEA_CONTAINER:/tmp/$DUMP_NAME" "$GITEA_DUMP_DIR/$DUMP_NAME"
docker exec -u git "$GITEA_CONTAINER" rm -f "/tmp/$DUMP_NAME"

[ -f "$GITEA_DUMP_DIR/$DUMP_NAME" ] || fail "A Gitea dump nem jött létre"

find "$GITEA_DUMP_DIR" -maxdepth 1 -type f -name 'gitea_*.zip' -printf '%T@ %p\n' \
  | sort -nr \
  | awk "NR > $GITEA_DUMP_KEEP {print \$2}" \
  | xargs -r rm -f

log "Gitea dump kész: $GITEA_DUMP_DIR/$DUMP_NAME"
