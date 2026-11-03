#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
BUNDLE="$BASE/secrets/homecontrol-secrets-latest.tar.gz.age"
AGE_IDENTITY_FILE="${AGE_IDENTITY_FILE:-$BASE/infra/ssh/homecontrol-secrets-age-key.txt}"
STAGING_ROOT="${HC_RESTORE_STAGING_DIR:-$BASE/restore_staging}"
APPLY=false
CONFIRM=false

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/restore_secrets_bundle.sh [bundle.age]
  scripts/restore_secrets_bundle.sh --apply --confirm [bundle.age]

Alapbol stagingbe bont. Eles gepre csak --apply --confirm mellett ir vissza.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply)
      APPLY=true
      shift
      ;;
    --confirm)
      CONFIRM=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      BUNDLE="$1"
      shift
      ;;
  esac
done

if ! command -v age >/dev/null 2>&1; then
  fail "age nem talalhato. Telepites Ubuntu alatt: sudo apt install age"
fi

[ -s "$BUNDLE" ] || fail "Secrets bundle nem talalhato: $BUNDLE"
[ -s "$AGE_IDENTITY_FILE" ] || fail "Age identity private key nem talalhato: $AGE_IDENTITY_FILE"

if [ "$APPLY" = "true" ]; then
  [ "$CONFIRM" = "true" ] || fail "Eles visszaallitashoz add meg: --apply --confirm"
  echo "Eles secrets restore indul: $BUNDLE -> /"
  age -d -i "$AGE_IDENTITY_FILE" "$BUNDLE" | tar -C / -xzf -
  echo "Eles secrets restore kesz"
else
  target="$STAGING_ROOT/secrets-$(date +%F_%H-%M-%S)/rootfs"
  mkdir -p "$target"
  echo "Staging secrets restore indul: $BUNDLE -> $target"
  age -d -i "$AGE_IDENTITY_FILE" "$BUNDLE" | tar -C "$target" -xzf -
  echo "Staging secrets restore kesz: $target"
  echo "Tartalomlista, ha elerheto: $target/SECRETS_BUNDLE_CONTENTS.txt"
fi
