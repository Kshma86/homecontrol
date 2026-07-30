#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="0.1"
REPO_URL="${REPO_URL:-https://github.com/Kshma86/homecontrol.git}"
REPO_REF="${REPO_REF:-main}"
BOOTSTRAP_DIR="${BOOTSTRAP_DIR:-/tmp/homecontrol-bootstrap}"
TARGET_BASE="${TARGET_BASE:-/srv/docker/homecontrol}"
WORK_ROOT="${WORK_ROOT:-/tmp/homecontrol-restore-v0.1}"
AGE_KEY_FILE="${AGE_KEY_FILE:-/root/emergency/homecontrol-secrets-age-key.txt}"
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-sftp:a@192.168.1.2:/mnt/hc-backup/restic/homecontrol}"
RESTIC_SNAPSHOT="${RESTIC_SNAPSHOT:-latest}"
MODE="full"
CONFIRM=false

log() {
  printf '[%(%Y-%m-%d %H:%M:%S)T] %s\n' -1 "$*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

usage() {
  cat >&2 <<EOF
HomeControl one-file restore launcher v${VERSION}

Usage:
  sudo $0 --confirm-new-hc-server [options]

Options:
  --age-key PATH              Saved age identity key. Default: ${AGE_KEY_FILE}
  --repo-url URL              GitHub/Gitea repo. Default: ${REPO_URL}
  --repo-ref REF              Branch/tag/commit. Default: ${REPO_REF}
  --bootstrap-dir DIR         Local clone dir. Default: ${BOOTSTRAP_DIR}
  --target DIR                Live target dir. Default: ${TARGET_BASE}
  --work-dir DIR              Staging/work dir. Default: ${WORK_ROOT}
  --restic-repo REPO          Restic repository. Default: ${RESTIC_REPOSITORY}
  --snapshot SNAPSHOT         Restic snapshot. Default: ${RESTIC_SNAPSHOT}
  --staging-only              Only prove clone/secrets/restic staging restore.
  --full                      Full restore, DB restore and stack start. Default.
  --confirm-new-hc-server     Required for full restore.
  -h, --help                  Show this help.

This launcher installs the minimal tools, clones/updates the HomeControl repo,
then executes scripts/bootstrap_restore_v0_1.sh from that repo.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --age-key)
      AGE_KEY_FILE="${2:-}"
      shift 2
      ;;
    --repo-url)
      REPO_URL="${2:-}"
      shift 2
      ;;
    --repo-ref)
      REPO_REF="${2:-}"
      shift 2
      ;;
    --bootstrap-dir)
      BOOTSTRAP_DIR="${2:-}"
      shift 2
      ;;
    --target)
      TARGET_BASE="${2:-}"
      shift 2
      ;;
    --work-dir)
      WORK_ROOT="${2:-}"
      shift 2
      ;;
    --restic-repo)
      RESTIC_REPOSITORY="${2:-}"
      shift 2
      ;;
    --snapshot)
      RESTIC_SNAPSHOT="${2:-}"
      shift 2
      ;;
    --staging-only)
      MODE="staging"
      shift
      ;;
    --full)
      MODE="full"
      shift
      ;;
    --confirm-new-hc-server)
      CONFIRM=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

[ "$(id -u)" -eq 0 ] || fail "Futtasd sudo-val/rootkent."
[ -s "$AGE_KEY_FILE" ] || fail "Age private key hianyzik vagy ures: $AGE_KEY_FILE"
[ -n "$REPO_URL" ] || fail "Repo URL ures"

if [ "$MODE" = "full" ] && [ "$CONFIRM" != "true" ]; then
  fail "Full restore-hoz kotelezo: --confirm-new-hc-server"
fi

log "HomeControl one-file restore launcher v${VERSION} indul"
log "Mode: $MODE"
log "Repo: $REPO_URL ref=$REPO_REF"
log "Target: $TARGET_BASE"

log "Minimalis bootstrap csomagok telepitese"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates git openssh-client

if [ -d "$BOOTSTRAP_DIR/.git" ]; then
  log "Meglevo bootstrap repo frissitese: $BOOTSTRAP_DIR"
  git -C "$BOOTSTRAP_DIR" fetch --all --prune
  git -C "$BOOTSTRAP_DIR" checkout "$REPO_REF"
  git -C "$BOOTSTRAP_DIR" pull --ff-only || true
else
  log "Bootstrap repo clone: $REPO_URL -> $BOOTSTRAP_DIR"
  mkdir -p "$(dirname "$BOOTSTRAP_DIR")"
  git clone "$REPO_URL" "$BOOTSTRAP_DIR"
  git -C "$BOOTSTRAP_DIR" checkout "$REPO_REF"
fi

bootstrap="$BOOTSTRAP_DIR/scripts/bootstrap_restore_v0_1.sh"
[ -x "$bootstrap" ] || fail "Bootstrap script nem futtathato: $bootstrap"

common_args=(
  --age-key "$AGE_KEY_FILE"
  --repo-url "$REPO_URL"
  --repo-ref "$REPO_REF"
  --target "$TARGET_BASE"
  --work-dir "$WORK_ROOT"
  --restic-repo "$RESTIC_REPOSITORY"
  --snapshot "$RESTIC_SNAPSHOT"
  --install-packages
)

if [ "$MODE" = "staging" ]; then
  "$bootstrap" "${common_args[@]}"
else
  "$bootstrap" "${common_args[@]}" \
    --apply \
    --apply-restic-files \
    --restore-db \
    --confirm-db-replace \
    --start
fi

log "HomeControl one-file restore launcher kesz"
