#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
GITEA_REMOTE="${GITEA_REMOTE:-ssh://git@192.168.1.2:2222/homecontrol/config.git}"
GITEA_SSH_KEY="${GITEA_SSH_KEY:-$BASE/infra/ssh/ai_node_key}"
GITEA_BRANCH="${GITEA_BRANCH:-main}"
WORK_DIR="$(mktemp -d /tmp/hc-gitea-status.XXXXXX)"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

export GIT_SSH_COMMAND="ssh -i $GITEA_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

echo "== Gitea config status =="
echo "Remote: $GITEA_REMOTE"
echo "Branch: $GITEA_BRANCH"

git clone --branch "$GITEA_BRANCH" "$GITEA_REMOTE" "$WORK_DIR/repo" >/dev/null
"$BASE/scripts/export_gitea_config_snapshot.sh" "$WORK_DIR/repo"

git -C "$WORK_DIR/repo" add -A
if git -C "$WORK_DIR/repo" diff --cached --quiet; then
  echo "Nincs változás a Gitea snapshothoz képest."
  exit 0
fi

echo
echo "Változások:"
git -C "$WORK_DIR/repo" status --short
echo
echo "Diff stat:"
git -C "$WORK_DIR/repo" diff --cached --stat
