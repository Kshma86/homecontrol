#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

BASE="${HC_PROJECT_ROOT:-/srv/docker/homecontrol}"
export BASE
CODE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$CODE_DIR/deployment_policy_cli.py" --worker-mode git
: "${HC_BACKUP_RUN_ID:?Use backup_runner.py}"
state() { python3 "$CODE_DIR/backup_job_state.py" "$@"; }
setting() { python3 - "$HC_BACKUP_SETTINGS_FILE" "$1" "$2" <<'PYSET'
import json,sys
value=json.load(open(sys.argv[1])).get(sys.argv[2],sys.argv[3])
print(str(value).lower() if isinstance(value,bool) else value)
PYSET
}
if [ "$(setting git_origin_enabled true)" != true ] || [ "$(setting backup_target ai_sftp)" = router_ftp ]; then
  exec bash "$CODE_DIR/backup_offsite_worker.sh" "$@"
fi
backup_host="$(setting ai_backup_host 192.168.1.2)"
repo_name="$(setting git_repository homecontrol/config)"
export GIT_TERMINAL_PROMPT=0
GITEA_REMOTE="${GITEA_REMOTE:-ssh://git@${backup_host}:2222/${repo_name}.git}"
GITEA_SSH_KEY="${GITEA_SSH_KEY:-$(setting ai_backup_ssh_key "$BASE/infra/ssh/ai_node_key")}"
GITEA_BRANCH="${GITEA_BRANCH:-main}"
GIT_OFFSITE_ENABLED="${GIT_OFFSITE_ENABLED:-$(setting git_offsite_enabled false)}"
GIT_OFFSITE_REMOTE="${GIT_OFFSITE_REMOTE:-$(setting git_offsite_remote "")}"
GIT_OFFSITE_BRANCH="${GIT_OFFSITE_BRANCH:-$(setting git_offsite_branch "$GITEA_BRANCH")}"
GIT_OFFSITE_TOKEN_FILE="${GIT_OFFSITE_TOKEN_FILE:-$(setting git_offsite_token_file "$BASE/infra/ssh/git-offsite-token")}"
GIT_OFFSITE_SSH_KEY="${GIT_OFFSITE_SSH_KEY:-$(setting git_offsite_ssh_key "")}"
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
    log "Offsite Git push hibás: nincs GIT_OFFSITE_REMOTE"
    return 1
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
    GIT_ASKPASS="$askpass" GIT_TERMINAL_PROMPT=0 git -C "$REPO" push -u offsite "$GITEA_BRANCH:$push_branch" || return $?
  elif [[ "$GIT_OFFSITE_REMOTE" == git@* || "$GIT_OFFSITE_REMOTE" == ssh://* ]] && [ -n "$GIT_OFFSITE_SSH_KEY" ]; then
    GIT_SSH_COMMAND="ssh -i $GIT_OFFSITE_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
      git -C "$REPO" push -u offsite "$GITEA_BRANCH:$push_branch" || return $?
  else
    GIT_TERMINAL_PROMPT=0 git -C "$REPO" push -u offsite "$GITEA_BRANCH:$push_branch" || return $?
  fi
  log "Offsite Git push kész"
}

state target gitea_origin running
if [ "$GIT_OFFSITE_ENABLED" = true ]; then
  state target git_offsite running
else
  state target git_offsite skipped "Offsite disabled"
fi
log "Config sync indul"
if ! git clone --branch "$GITEA_BRANCH" "$GITEA_REMOTE" "$WORK_DIR/repo" >/dev/null 2>&1; then
  rm -rf "$WORK_DIR/repo"
  mkdir -p "$WORK_DIR/repo"
  git -C "$WORK_DIR/repo" init
  git -C "$WORK_DIR/repo" checkout -b "$GITEA_BRANCH"
fi
REPO="$WORK_DIR/repo"
git -C "$REPO" remote remove origin >/dev/null 2>&1 || true
git -C "$REPO" remote add origin "$GITEA_REMOTE"
git -C "$REPO" config user.name "HomeControl Backup"
git -C "$REPO" config user.email "backup@homecontrol.local"

# Export policy is unchanged here (HC-17/18 remain deployment dependencies).
if ! python3 "$BASE/scripts/export_config_snapshot.py" "$REPO"; then
  state target gitea_origin failed "Configuration export failed"
  [ "$GIT_OFFSITE_ENABLED" != true ] || state target git_offsite failed "Configuration export failed"
  exit 1
fi
git -C "$REPO" add -A
if ! git -C "$REPO" diff --cached --quiet; then
  git -C "$REPO" commit -m "$COMMIT_MESSAGE"
fi
status=0
if git -C "$REPO" push -u origin "$GITEA_BRANCH"; then
  state target gitea_origin succeeded
else
  state target gitea_origin failed "Origin push failed"
  status=1
fi
# Always try the independently configured destination even after an origin error.
if [ "$GIT_OFFSITE_ENABLED" = true ]; then
  if offsite_push; then
    state target git_offsite succeeded
  else
    state target git_offsite failed "Offsite push failed"
    status=1
  fi
fi
[ "$status" -ne 0 ] || log "Config sync kész"
exit "$status"
