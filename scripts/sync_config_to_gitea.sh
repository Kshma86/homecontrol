#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
GITEA_REMOTE="${GITEA_REMOTE:-ssh://git@192.168.1.2:2222/homecontrol/config.git}"
GITEA_SSH_KEY="${GITEA_SSH_KEY:-$BASE/infra/ssh/ai_node_key}"
GITEA_BRANCH="${GITEA_BRANCH:-main}"
COMMIT_MESSAGE="${1:-${GITEA_COMMIT_MESSAGE:-Update HomeControl configuration snapshot}}"
WORK_DIR="$(mktemp -d /tmp/hc-gitea-config.XXXXXX)"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

log() {
  echo "[$(date '+%F %T')] $*"
}

export GIT_SSH_COMMAND="ssh -i $GITEA_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

log "Config sync indul: $GITEA_REMOTE branch=$GITEA_BRANCH"
if ! git clone "$GITEA_REMOTE" "$WORK_DIR/repo" >/dev/null 2>&1; then
  mkdir -p "$WORK_DIR/repo"
  git -C "$WORK_DIR/repo" init
  git -C "$WORK_DIR/repo" remote add origin "$GITEA_REMOTE"
  git -C "$WORK_DIR/repo" checkout -b "$GITEA_BRANCH"
else
  git -C "$WORK_DIR/repo" checkout "$GITEA_BRANCH" >/dev/null 2>&1 || git -C "$WORK_DIR/repo" checkout -b "$GITEA_BRANCH"
fi

REPO="$WORK_DIR/repo"
git -C "$REPO" config user.name "HomeControl Backup"
git -C "$REPO" config user.email "backup@homecontrol.local"

"$BASE/scripts/export_gitea_config_snapshot.sh" "$REPO"

git -C "$REPO" add -A
if git -C "$REPO" diff --cached --quiet; then
  log "Nincs változás, push kihagyva"
  exit 0
fi

git -C "$REPO" commit -m "$COMMIT_MESSAGE"
git -C "$REPO" push -u origin "$GITEA_BRANCH"
log "Config sync kész"
