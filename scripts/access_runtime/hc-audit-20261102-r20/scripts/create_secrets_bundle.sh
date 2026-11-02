#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
MANIFEST="${SECRETS_MANIFEST:-$BASE/secrets/manifest.txt}"
OUT_DIR="${SECRETS_OUT_DIR:-$BASE/secrets}"
AGE_KEY_FILE="${AGE_KEY_FILE:-$BASE/infra/ssh/homecontrol-secrets-age-key.txt}"
STRICT_SECRETS="${STRICT_SECRETS:-false}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

log() {
  printf '[%(%Y-%m-%d %H:%M:%S)T] %s\n' -1 "$*"
}

if ! command -v age >/dev/null 2>&1; then
  fail "age nem talalhato. Telepites Ubuntu alatt: sudo apt install age"
fi

[ -s "$MANIFEST" ] || fail "Secrets manifest nem talalhato: $MANIFEST"

recipient="${AGE_RECIPIENT:-}"
if [ -z "$recipient" ] && [ -s "$OUT_DIR/age-recipient.txt" ]; then
  recipient="$(sed '/^[[:space:]]*$/d; /^[[:space:]]*#/d; q' "$OUT_DIR/age-recipient.txt" || true)"
fi
if [ -z "$recipient" ] && [ -s "$AGE_KEY_FILE" ]; then
  recipient="$(sed -n 's/^# public key: //p' "$AGE_KEY_FILE" | head -n 1)"
fi
[ -n "$recipient" ] || fail "Nincs age recipient. Futtasd: scripts/init_secrets_age_key.sh"

install -d -m 755 "$OUT_DIR"
timestamp="$(date +%F_%H-%M-%S)"
output="$OUT_DIR/homecontrol-secrets-$timestamp.tar.gz.age"
latest="$OUT_DIR/homecontrol-secrets-latest.tar.gz.age"
work="$(mktemp -d /tmp/hc-secrets-bundle.XXXXXX)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/rootfs"

copied=0
missing=0

while IFS= read -r raw_line || [ -n "$raw_line" ]; do
  line="${raw_line#"${raw_line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [ -n "$line" ] || continue
  case "$line" in
    \#*) continue ;;
  esac

  if [[ "$line" = /* ]]; then
    source="$line"
    rel="${line#/}"
  else
    source="$BASE/$line"
    rel="${BASE#/}/$line"
  fi

  if [ ! -e "$source" ]; then
    log "-- Hianyzo secrets elem kihagyva: $source"
    missing=$((missing + 1))
    continue
  fi

  target="$work/rootfs/$rel"
  mkdir -p "$(dirname "$target")"
  cp -a "$source" "$target"
  printf '/%s\n' "$rel" >> "$work/SECRETS_BUNDLE_CONTENTS.txt"
  copied=$((copied + 1))
done < "$MANIFEST"

if [ "$copied" -eq 0 ]; then
  fail "Egyetlen secrets elem sem kerult a bundle-be"
fi

if [ "$missing" -gt 0 ] && [ "$STRICT_SECRETS" = "true" ]; then
  fail "$missing secrets elem hianyzik, STRICT_SECRETS=true miatt megszakitva"
fi

{
  echo "created_at=$(date -Is)"
  echo "host=$(hostname)"
  echo "base=$BASE"
  echo "copied=$copied"
  echo "missing=$missing"
} > "$work/rootfs/SECRETS_BUNDLE_METADATA.txt"
cp "$work/SECRETS_BUNDLE_CONTENTS.txt" "$work/rootfs/SECRETS_BUNDLE_CONTENTS.txt"

log "Secrets bundle keszul: $output"
tar -C "$work/rootfs" -czf - . | age -r "$recipient" -o "$output"
chmod 644 "$output"
(cd "$OUT_DIR" && sha256sum "$(basename "$output")" > "$(basename "$output").sha256")
chmod 644 "$output.sha256"

cp -a "$output" "$latest"
(cd "$OUT_DIR" && sha256sum "$(basename "$latest")" > "$(basename "$latest").sha256")
chmod 644 "$latest"
chmod 644 "$latest.sha256"

log "Secrets bundle kesz: $output"
log "Latest masolat: $latest"
if [ "$missing" -gt 0 ]; then
  log "Figyelem: $missing manifest elem hianyzott. Reszletek a fenti logban."
fi
