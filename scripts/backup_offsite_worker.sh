#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
CODE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE="${HC_PROJECT_ROOT:-/srv/docker/homecontrol}"
export BASE
python3 "$CODE_DIR/deployment_policy_cli.py" --worker-mode git
: "${HC_BACKUP_RUN_ID:?Use the common host runner}"
state() { python3 "$CODE_DIR/backup_job_state.py" "$@"; }
setting() { python3 - "$HC_BACKUP_SETTINGS_FILE" "$1" "$2" <<'PY'
import json,sys
value=json.load(open(sys.argv[1])).get(sys.argv[2],sys.argv[3])
print(str(value).lower() if isinstance(value,bool) else value)
PY
}
state target gitea_origin skipped "AI Gitea disabled; external Git only"
state target git_offsite running
WORK_DIR="$(mktemp -d /tmp/hc-offsite.XXXXXXXX)"
finish() {
  status=$?
  if [ "$status" -ne 0 ]; then state target git_offsite failed "External Git export/push failed" || true; fi
  rm -rf "$WORK_DIR"
}
trap finish EXIT
[ "$(setting git_offsite_enabled false)" = true ] || exit 1
remote="$(setting git_offsite_remote '')"
branch="$(setting git_offsite_branch main)"
export GIT_OFFSITE_TOKEN_FILE="$(setting git_offsite_token_file '')"
key="$(setting git_offsite_ssh_key '')"
[ -n "$remote" ] && [[ "$remote" != -* ]] || exit 1
# URL credentials must remain in the private token/key file.
python3 - "$remote" <<'PY'
import sys
from urllib.parse import urlsplit
remote=sys.argv[1]
if '://' in remote:
    parsed=urlsplit(remote)
    if parsed.scheme not in ('https','ssh') or parsed.password or (parsed.scheme=='https' and parsed.username):
        raise SystemExit('Use a Git remote without embedded credentials')
PY
git check-ref-format --branch "$branch" >/dev/null
export GIT_TERMINAL_PROMPT=0
unset GIT_SSH_COMMAND GIT_ASKPASS SSH_ASKPASS
if [[ "$remote" == https://* ]] && [ -f "$GIT_OFFSITE_TOKEN_FILE" ]; then
  cat > "$WORK_DIR/askpass" <<'ASKPASS'
#!/usr/bin/env bash
case "$1" in
  *Username*) printf '%s\n' x-access-token ;;
  *Password*) cat "$GIT_OFFSITE_TOKEN_FILE" ;;
esac
ASKPASS
  chmod 700 "$WORK_DIR/askpass"
  export GIT_ASKPASS="$WORK_DIR/askpass"
elif [ -n "$key" ]; then
  # shlex avoids interpreting spaces/metacharacters in an admin-configured key path.
  export GIT_SSH_COMMAND="$(python3 - "$key" <<'PY'
import shlex,sys
print('ssh -i '+shlex.quote(sys.argv[1])+' -o BatchMode=yes -o StrictHostKeyChecking=accept-new')
PY
)"
fi
repo="$WORK_DIR/repo"
if ! git clone --branch "$branch" -- "$remote" "$repo" >/dev/null 2>&1; then
  # Only a positively reachable, empty repository may start a new history.
  heads="$(git ls-remote --heads -- "$remote")"
  [ -z "$heads" ] || exit 1
  mkdir -p "$repo"
  git -C "$repo" init -b "$branch" >/dev/null
  git -C "$repo" remote add origin "$remote"
fi
git -C "$repo" config user.name 'HomeControl Backup'
git -C "$repo" config user.email backup@homecontrol.local
python3 "$CODE_DIR/export_config_snapshot.py" "$repo"
python3 "$CODE_DIR/export_config_snapshot.py" --stage-only "$repo"
if ! git -C "$repo" diff --cached --quiet; then
  git -C "$repo" commit -m "${1:-${GITEA_COMMIT_MESSAGE:-Update HomeControl configuration snapshot}}" >/dev/null
fi
# No force push, no AI remote, and the second run clones this same history.
git -C "$repo" push -u origin "$branch" >/dev/null 2>&1
state target git_offsite succeeded
