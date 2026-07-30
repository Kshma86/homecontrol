#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="0.1"
TARGET_BASE="${TARGET_BASE:-/srv/docker/homecontrol}"
WORK_ROOT="${WORK_ROOT:-/tmp/homecontrol-restore-v0.1}"
REPO_URL="${REPO_URL:-https://github.com/Kshma86/homecontrol.git}"
REPO_REF="${REPO_REF:-main}"
RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-sftp:a@192.168.1.2:/mnt/hc-backup/restic/homecontrol}"
RESTIC_SNAPSHOT="${RESTIC_SNAPSHOT:-latest}"
AGE_KEY_FILE="${AGE_KEY_FILE:-}"

INSTALL_PACKAGES=false
APPLY=false
APPLY_RESTIC_FILES=false
START_STACK=false
RESTORE_RESTIC=true
RESTORE_DB=false
CONFIRM_DB_REPLACE=false

log() {
  printf '[%(%Y-%m-%d %H:%M:%S)T] %s\n' -1 "$*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

usage() {
  cat >&2 <<EOF
HomeControl disaster restore bootstrap v${VERSION}

Usage:
  $0 --age-key /path/to/homecontrol-secrets-age-key.txt [options]

Options:
  --repo-url URL              Git repo to clone. Default: ${REPO_URL}
  --repo-ref REF              Branch/tag/commit to restore. Default: ${REPO_REF}
  --target DIR                Live HomeControl target. Default: ${TARGET_BASE}
  --work-dir DIR              Restore work/staging dir. Default: ${WORK_ROOT}
  --restic-repo REPO          Restic repository. Default: ${RESTIC_REPOSITORY}
  --snapshot SNAPSHOT         Restic snapshot id/ref. Default: ${RESTIC_SNAPSHOT}
  --install-packages          Install Ubuntu packages with apt-get.
  --skip-restic               Skip restic restore.
  --apply                     Copy project and secrets to live target paths.
  --apply-restic-files        Also overlay restic-restored HC files to target.
  --restore-db                Restore PostgreSQL dump from latest archive.
  --confirm-db-replace        Required with --restore-db; drops/recreates DB.
  --start                     Start Docker Compose stacks after apply.
  -h, --help                  Show this help.

Default mode is staging-only: it clones the project, decrypts secrets to a
staging root, and restores restic to a staging directory. Live paths are changed
only with --apply, and DB replacement needs both --restore-db and
--confirm-db-replace.
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
    --install-packages)
      INSTALL_PACKAGES=true
      shift
      ;;
    --skip-restic)
      RESTORE_RESTIC=false
      shift
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    --apply-restic-files)
      APPLY_RESTIC_FILES=true
      shift
      ;;
    --restore-db)
      RESTORE_DB=true
      shift
      ;;
    --confirm-db-replace)
      CONFIRM_DB_REPLACE=true
      shift
      ;;
    --start)
      START_STACK=true
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

[ -n "$AGE_KEY_FILE" ] || fail "--age-key kotelezo. Add meg a kulon lementett age identity private key fajlt."
[ -s "$AGE_KEY_FILE" ] || fail "Age identity private key nem talalhato vagy ures: $AGE_KEY_FILE"
[ -n "$REPO_URL" ] || fail "Repo URL ures"
[ -n "$TARGET_BASE" ] || fail "Target ures"

if [ "$RESTORE_DB" = "true" ] && [ "$CONFIRM_DB_REPLACE" != "true" ]; then
  fail "--restore-db csak --confirm-db-replace mellett engedett"
fi

if [ "$START_STACK" = "true" ] && [ "$APPLY" != "true" ]; then
  fail "--start csak --apply mellett ertelmes"
fi

if [ "$APPLY_RESTIC_FILES" = "true" ] && [ "$APPLY" != "true" ]; then
  fail "--apply-restic-files csak --apply mellett ertelmes"
fi

if [ "$APPLY_RESTIC_FILES" = "true" ] && [ "$RESTORE_RESTIC" != "true" ]; then
  fail "--apply-restic-files nem hasznalhato --skip-restic mellett"
fi

if [ "$APPLY" = "true" ] && [ "$(id -u)" -ne 0 ]; then
  fail "--apply modhoz root kell. Futtasd sudo-val."
fi

PROJECT_DIR="$WORK_ROOT/project"
SECRETS_ROOT="$WORK_ROOT/secrets/rootfs"
RESTIC_TARGET="$WORK_ROOT/restic"
ARCHIVE_STAGE="$WORK_ROOT/archive"

install_packages() {
  log "Ubuntu csomagok telepitese"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    age \
    ca-certificates \
    curl \
    git \
    openssh-client \
    restic \
    rsync \
    tar

  if ! command -v docker >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
  fi

  if ! docker compose version >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-v2 || true
  fi

  if ! docker compose version >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin || true
  fi
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Hianyzo parancs: $1"
}

env_value() {
  local key="$1"
  local default="$2"
  local file="$TARGET_BASE/infra/.env"
  if [ -f "$file" ]; then
    local value
    value="$(sed -n "s/^${key}=//p" "$file" | tail -n 1)"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    if [ -n "$value" ]; then
      printf '%s\n' "$value"
      return 0
    fi
  fi
  printf '%s\n' "$default"
}

clone_project() {
  mkdir -p "$WORK_ROOT"
  if [ -d "$PROJECT_DIR/.git" ]; then
    log "Project staging mar letezik, frissites: $PROJECT_DIR"
    git -C "$PROJECT_DIR" fetch --all --prune
    git -C "$PROJECT_DIR" checkout "$REPO_REF"
    git -C "$PROJECT_DIR" pull --ff-only || true
  else
    log "Project clone: $REPO_URL -> $PROJECT_DIR"
    git clone "$REPO_URL" "$PROJECT_DIR"
    git -C "$PROJECT_DIR" checkout "$REPO_REF"
  fi
}

verify_bundle() {
  local bundle="$PROJECT_DIR/secrets/homecontrol-secrets-latest.tar.gz.age"
  local checksum="$bundle.sha256"
  [ -s "$bundle" ] || fail "Encrypted secrets bundle hianyzik: $bundle"
  [ -s "$checksum" ] || fail "Secrets checksum hianyzik: $checksum"
  local expected actual
  expected="$(awk 'NR == 1 {print $1}' "$checksum")"
  actual="$(sha256sum "$bundle" | awk '{print $1}')"
  [ -n "$expected" ] || fail "Secrets checksum ures vagy olvashatatlan: $checksum"
  if [ "$expected" != "$actual" ]; then
    fail "Secrets checksum nem egyezik: $bundle"
  fi
  log "Secrets checksum OK: $bundle"
}

decrypt_secrets_to_staging() {
  local bundle="$PROJECT_DIR/secrets/homecontrol-secrets-latest.tar.gz.age"
  log "Secrets decrypt stagingbe: $SECRETS_ROOT"
  mkdir -p "$SECRETS_ROOT"
  age -d -i "$AGE_KEY_FILE" "$bundle" | tar -C "$SECRETS_ROOT" -xzf -
  [ -f "$SECRETS_ROOT/SECRETS_BUNDLE_CONTENTS.txt" ] || fail "Secrets tartalomlista hianyzik a stagingben"
}

apply_project() {
  log "Project apply: $PROJECT_DIR -> $TARGET_BASE"
  mkdir -p "$TARGET_BASE"
  rsync -a \
    --exclude '.git' \
    "$PROJECT_DIR/" "$TARGET_BASE/"
}

apply_restic_files() {
  [ "$APPLY_RESTIC_FILES" = "true" ] || return 0
  local source="$RESTIC_TARGET/$TARGET_BASE"
  [ -d "$source" ] || fail "Restic HC staging konyvtar hianyzik: $source"
  log "Restic file apply: $source -> $TARGET_BASE"
  mkdir -p "$TARGET_BASE"
  rsync -a \
    --exclude 'infra/postgres/data' \
    --exclude 'infra/mqtt/data' \
    --exclude 'infra/mqtt/log' \
    --exclude 'infra/zigbee2mqtt/data/log' \
    --exclude 'apps/tuya-poller/logs' \
    "$source/" "$TARGET_BASE/"
}

stop_existing_stacks_for_apply() {
  [ "$APPLY" = "true" ] || return 0
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if [ -f "$TARGET_BASE/homeassistant/docker-compose.yml" ]; then
    log "Meglevo Home Assistant stack leallitasa restore elott"
    (cd "$TARGET_BASE/homeassistant" && docker compose down) || true
  fi
  if [ -f "$TARGET_BASE/infra/docker-compose.yml" ]; then
    log "Meglevo infra stack leallitasa restore elott"
    (cd "$TARGET_BASE/infra" && docker compose down) || true
  fi
}

apply_secrets() {
  local bundle="$PROJECT_DIR/secrets/homecontrol-secrets-latest.tar.gz.age"
  log "Secrets apply: encrypted bundle -> /"
  age -d -i "$AGE_KEY_FILE" "$bundle" | tar -C / -xzf -
  chmod 600 "$TARGET_BASE/infra/ssh/"*_key 2>/dev/null || true
  chmod 600 "$TARGET_BASE/infra/ssh/"*-key.txt 2>/dev/null || true
  chmod 600 /etc/homecontrol/restic-password 2>/dev/null || true
}

restore_restic_to_staging() {
  if [ "$RESTORE_RESTIC" != "true" ]; then
    log "Restic restore kihagyva"
    return 0
  fi

  local restic_password="$SECRETS_ROOT/etc/homecontrol/restic-password"
  local ai_key="$SECRETS_ROOT/srv/docker/homecontrol/infra/ssh/ai_node_key"
  local sftp_target=""
  [ -s "$restic_password" ] || fail "Restic password hianyzik a secrets stagingbol: $restic_password"
  [ -s "$ai_key" ] || fail "AI SSH key hianyzik a secrets stagingbol: $ai_key"
  if [[ "$RESTIC_REPOSITORY" =~ ^sftp:([^:]+): ]]; then
    sftp_target="${BASH_REMATCH[1]}"
  fi
  [ -n "$sftp_target" ] || fail "Nem tudom kiolvasni az SFTP cel hostot a restic repo-bol: $RESTIC_REPOSITORY"

  chmod 600 "$ai_key"
  export RESTIC_PASSWORD_FILE="$restic_password"
  export RESTIC_CACHE_DIR="$WORK_ROOT/restic-cache"
  RESTIC_ARGS=(
    -r "$RESTIC_REPOSITORY"
    -o "sftp.command=ssh -i $ai_key -o BatchMode=yes -o StrictHostKeyChecking=accept-new $sftp_target -s sftp"
  )

  log "Restic snapshots ellenorzes: $RESTIC_REPOSITORY"
  restic "${RESTIC_ARGS[@]}" snapshots --tag homecontrol >/dev/null

  log "Restic restore stagingbe: snapshot=$RESTIC_SNAPSHOT target=$RESTIC_TARGET"
  if [ -e "$RESTIC_TARGET" ]; then
    previous="${RESTIC_TARGET}.previous-$(date +%F_%H-%M-%S)"
    log "Meglevo restic staging felrerakasa: $RESTIC_TARGET -> $previous"
    mv "$RESTIC_TARGET" "$previous"
  fi
  mkdir -p "$RESTIC_TARGET"
  restic "${RESTIC_ARGS[@]}" restore "$RESTIC_SNAPSHOT" --target "$RESTIC_TARGET" --tag homecontrol
}

latest_archive_from_restic() {
  find "$RESTIC_TARGET/$TARGET_BASE/backups" -maxdepth 1 -type f -name 'homecontrol_*.tar.gz' 2>/dev/null | sort | tail -n 1
}

extract_latest_archive() {
  local archive
  archive="$(latest_archive_from_restic)"
  [ -n "$archive" ] || fail "Nem talalhato homecontrol_*.tar.gz archívum a restic stagingben"
  log "Legfrissebb HC archive kibontas stagingbe: $archive"
  mkdir -p "$ARCHIVE_STAGE"
  tar -xzf "$archive" -C "$ARCHIVE_STAGE"
}

latest_db_dump() {
  find "$ARCHIVE_STAGE" -type f -path '*/postgres/*.dump' | sort | tail -n 1
}

restore_database() {
  [ "$RESTORE_DB" = "true" ] || return 0
  [ "$APPLY" = "true" ] || fail "--restore-db csak --apply mellett futtathato"

  extract_latest_archive
  local dump
  dump="$(latest_db_dump)"
  [ -s "$dump" ] || fail "Nem talalhato PostgreSQL dump a kibontott archive-ban"

  local db_user db_name
  db_user="$(env_value POSTGRES_USER homecontrol)"
  db_name="$(env_value POSTGRES_DB homecontrol)"

  log "PostgreSQL kontener inditasa DB restore-hoz"
  (cd "$TARGET_BASE/infra" && docker compose up -d postgres pgbouncer)

  log "PostgreSQL health varakozas"
  for _ in $(seq 1 60); do
    if docker exec homecontrol-postgres pg_isready -U "$db_user" -d postgres >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  docker exec homecontrol-postgres pg_isready -U "$db_user" -d postgres >/dev/null 2>&1 \
    || fail "PostgreSQL nem lett elerheto"

  log "DB csere indul: $db_name"
  docker cp "$dump" homecontrol-postgres:/tmp/homecontrol_restore.dump
  docker exec homecontrol-postgres psql -U "$db_user" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${db_name}' AND pid <> pg_backend_pid();"
  docker exec homecontrol-postgres dropdb -U "$db_user" --if-exists "$db_name"
  docker exec homecontrol-postgres createdb -U "$db_user" "$db_name"
  docker exec homecontrol-postgres pg_restore -U "$db_user" -d "$db_name" /tmp/homecontrol_restore.dump
  docker exec homecontrol-postgres rm -f /tmp/homecontrol_restore.dump
  log "DB restore kesz: $db_name"
}

start_stacks() {
  [ "$START_STACK" = "true" ] || return 0
  [ "$APPLY" = "true" ] || fail "--start csak --apply mellett futtathato"
  local ha_growatt_token
  ha_growatt_token="$(env_value HA_GROWATT_TOKEN "")"
  log "Docker compose stack inditas: infra"
  (cd "$TARGET_BASE/infra" && docker compose up -d --build)
  if [ -n "$ha_growatt_token" ]; then
    log "Docker compose profil inditas: ha-growatt"
    (cd "$TARGET_BASE/infra" && docker compose --profile ha-growatt up -d --build homecontrol-ha-growatt-poller)
  fi
  if [ -f "$TARGET_BASE/homeassistant/docker-compose.yml" ]; then
    log "Docker compose stack inditas: homeassistant"
    (cd "$TARGET_BASE/homeassistant" && docker compose up -d)
  fi
}

summary() {
  log "Restore bootstrap v${VERSION} kesz"
  echo
  echo "Staging:"
  echo "  project: $PROJECT_DIR"
  echo "  secrets: $SECRETS_ROOT"
  echo "  restic:  $RESTIC_TARGET"
  echo
  if [ "$APPLY" != "true" ]; then
    echo "Eles fajlok nem valtoztak. Eles futtatashoz:"
    echo "  sudo $0 --age-key /path/to/key --apply"
    echo
    echo "DB restore-hoz csak friss gepen vagy tudatos csere mellett:"
    echo "  sudo $0 --age-key /path/to/key --apply --restore-db --confirm-db-replace --start"
  else
    echo "Eles target frissitve: $TARGET_BASE"
  fi
}

main() {
  log "HomeControl disaster restore bootstrap v${VERSION} indul"
  if [ "$INSTALL_PACKAGES" = "true" ]; then
    [ "$(id -u)" -eq 0 ] || fail "--install-packages root jogot igenyel"
    install_packages
  fi

  need_command git
  need_command age
  need_command tar
  need_command rsync
  if [ "$RESTORE_RESTIC" = "true" ]; then
    need_command restic
    need_command ssh
  fi
  if [ "$APPLY" = "true" ] || [ "$START_STACK" = "true" ] || [ "$RESTORE_DB" = "true" ]; then
    need_command docker
  fi

  clone_project
  verify_bundle
  decrypt_secrets_to_staging

  restore_restic_to_staging

  if [ "$APPLY" = "true" ]; then
    stop_existing_stacks_for_apply
    apply_restic_files
    apply_project
    apply_secrets
  fi

  if [ "$RESTORE_DB" = "true" ]; then
    restore_database
  elif [ "$RESTORE_RESTIC" = "true" ]; then
    extract_latest_archive || log "Archive kibontas kihagyva: nincs restic archive stagingben"
  fi
  start_stacks
  summary
}

main
