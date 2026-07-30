#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
GITEA_REMOTE="${GITEA_REMOTE:-ssh://git@192.168.1.2:2222/homecontrol/config.git}"
GITEA_SSH_KEY="${GITEA_SSH_KEY:-$BASE/infra/ssh/ai_node_key}"
GITEA_BRANCH="${GITEA_BRANCH:-main}"
GIT_OFFSITE_ENABLED="${GIT_OFFSITE_ENABLED:-false}"
GIT_OFFSITE_REMOTE="${GIT_OFFSITE_REMOTE:-}"
GIT_OFFSITE_BRANCH="${GIT_OFFSITE_BRANCH:-$GITEA_BRANCH}"
GIT_OFFSITE_TOKEN_FILE="${GIT_OFFSITE_TOKEN_FILE:-$BASE/infra/ssh/git-offsite-token}"
GIT_OFFSITE_SSH_KEY="${GIT_OFFSITE_SSH_KEY:-}"
COMMIT_MESSAGE="${1:-${GITEA_COMMIT_MESSAGE:-Update HomeControl configuration snapshot}}"
WORK_DIR="$(mktemp -d /tmp/hc-gitea-config.XXXXXX)"
export GIT_OFFSITE_TOKEN_FILE

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

log() {
  echo "[$(date '+%F %T')] $*"
}

export GIT_SSH_COMMAND="ssh -i $GITEA_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

offsite_push() {
  if [ "$GIT_OFFSITE_ENABLED" != "true" ] && [ "$GIT_OFFSITE_ENABLED" != "1" ]; then
    return 0
  fi
  if [ -z "$GIT_OFFSITE_REMOTE" ]; then
    log "Offsite Git push kihagyva: nincs GIT_OFFSITE_REMOTE"
    return 0
  fi

  git -C "$REPO" remote remove offsite >/dev/null 2>&1 || true
  git -C "$REPO" remote add offsite "$GIT_OFFSITE_REMOTE"

  local push_branch="${GIT_OFFSITE_BRANCH:-$GITEA_BRANCH}"
  log "Offsite Git push indul: branch=$push_branch"
  if [[ "$GIT_OFFSITE_REMOTE" == https://* ]] && [ -f "$GIT_OFFSITE_TOKEN_FILE" ]; then
    local askpass="$WORK_DIR/git-offsite-askpass.sh"
    cat > "$askpass" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  *Username*) printf '%s\n' x-access-token ;;
  *Password*) cat "$GIT_OFFSITE_TOKEN_FILE" ;;
  *) printf '\n' ;;
esac
EOF
    chmod 700 "$askpass"
    GIT_ASKPASS="$askpass" GIT_TERMINAL_PROMPT=0 git -C "$REPO" push -u offsite "$GITEA_BRANCH:$push_branch"
  elif [[ "$GIT_OFFSITE_REMOTE" == git@* || "$GIT_OFFSITE_REMOTE" == ssh://* ]] && [ -n "$GIT_OFFSITE_SSH_KEY" ]; then
    GIT_SSH_COMMAND="ssh -i $GIT_OFFSITE_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
      git -C "$REPO" push -u offsite "$GITEA_BRANCH:$push_branch"
  else
    GIT_TERMINAL_PROMPT=0 git -C "$REPO" push -u offsite "$GITEA_BRANCH:$push_branch"
  fi
  log "Offsite Git push kész"
}

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
  offsite_push
  exit 0
fi

git -C "$REPO" commit -m "$COMMIT_MESSAGE"
git -C "$REPO" push -u origin "$GITEA_BRANCH"
offsite_push
log "Config sync kész"
