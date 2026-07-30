#!/usr/bin/env bash
set -Eeuo pipefail

LOCAL_BASE="${LOCAL_BASE:-/srv/docker/homecontrol}"
REMOTE_BASE="${REMOTE_BASE:-/srv/docker/homecontrol}"
REMOTE_HOST=""
MODE="project"
OUT_DIR="${OUT_DIR:-/tmp/homecontrol-tree-compare}"

usage() {
  cat <<EOF
HomeControl restore tree compare

Usage:
  scripts/compare_restore_tree.sh a@192.168.1.161 [options]

Options:
  --local-base DIR     Local HC path. Default: ${LOCAL_BASE}
  --remote-base DIR    Remote HC path. Default: ${REMOTE_BASE}
  --mode MODE          project or full-ish. Default: ${MODE}
  --out-dir DIR        Output dir. Default: ${OUT_DIR}
  -h, --help           Show this help.

Modes:
  project   Compares source/config files and excludes runtime data, logs,
            backups, restore staging, raw secrets, DB data and docker volumes.
  full-ish  Compares a broader tree, but still excludes .git, backups,
            restore staging and unreadable/runtime-heavy Docker internals.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --local-base)
      LOCAL_BASE="${2:-}"
      shift 2
      ;;
    --remote-base)
      REMOTE_BASE="${2:-}"
      shift 2
      ;;
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ -n "$REMOTE_HOST" ]; then
        echo "Remote host already set: $REMOTE_HOST" >&2
        exit 2
      fi
      REMOTE_HOST="$1"
      shift
      ;;
  esac
done

[ -n "$REMOTE_HOST" ] || { usage >&2; exit 2; }
[ -d "$LOCAL_BASE" ] || { echo "Local base missing: $LOCAL_BASE" >&2; exit 1; }

case "$MODE" in
  project|full-ish) ;;
  *) echo "Unsupported mode: $MODE" >&2; exit 2 ;;
esac

mkdir -p "$OUT_DIR"

collect_script='
set -Eeuo pipefail
base="$1"
mode="$2"
cd "$base"

find_args=(
  . -path "./.git" -prune
  -o -path "./backups" -prune
  -o -path "./restore_staging" -prune
  -o -path "./*/__pycache__" -prune
  -o -path "./*/node_modules" -prune
)

if [ "$mode" = "project" ]; then
  find_args+=(
    -o -path "./infra/postgres/data" -prune
    -o -path "./infra/mqtt/data" -prune
    -o -path "./infra/mqtt/log" -prune
    -o -path "./infra/zigbee2mqtt/data/log" -prune
    -o -path "./apps/tuya-poller/logs" -prune
    -o -path "./secrets" -prune
    -o -path "./infra/ssh" -prune
    -o -path "./homeassistant/config/.storage" -prune
    -o -path "./homeassistant/config/deps" -prune
    -o -path "./homeassistant/config/tts" -prune
  )
fi

find "${find_args[@]}" -o -type f -print0 |
  LC_ALL=C sort -z |
  while IFS= read -r -d "" file; do
    rel="${file#./}"
    if [ "$mode" = "project" ]; then
      case "$rel" in
        *.db|*.db-*|*.log|*.log.*|*.log.fault|*.tar.gz|*.tmp|*.pid|*.lock|homeassistant/config/.HA_VERSION|infra/zigbee2mqtt/data/database.db|infra/zigbee2mqtt/data/state.json|apps/xiaomi-x10/x10_maps/map_object_*.json)
          continue
          ;;
      esac
    fi
    bytes="$(wc -c < "$file" 2>/dev/null || printf unreadable)"
    lines="$(wc -l < "$file" 2>/dev/null || printf unreadable)"
    sha="$(sha256sum "$file" 2>/dev/null | awk "{print \$1}" || printf unreadable)"
    printf "%s\t%s\t%s\t%s\n" "$sha" "$bytes" "$lines" "$rel"
  done
'

local_manifest="$OUT_DIR/local.tsv"
remote_manifest="$OUT_DIR/remote.tsv"
local_paths="$OUT_DIR/local.paths"
remote_paths="$OUT_DIR/remote.paths"

bash -c "$collect_script" bash "$LOCAL_BASE" "$MODE" > "$local_manifest"
ssh -o StrictHostKeyChecking=accept-new "$REMOTE_HOST" \
  "bash -s -- '$REMOTE_BASE' '$MODE'" <<< "$collect_script" > "$remote_manifest"

cut -f4- "$local_manifest" > "$local_paths"
cut -f4- "$remote_manifest" > "$remote_paths"

echo "== Summary =="
printf "mode:         %s\n" "$MODE"
printf "local base:   %s\n" "$LOCAL_BASE"
printf "remote base:  %s:%s\n" "$REMOTE_HOST" "$REMOTE_BASE"
printf "local files:  %s\n" "$(wc -l < "$local_paths")"
printf "remote files: %s\n" "$(wc -l < "$remote_paths")"
printf "local lines:  %s\n" "$(awk -F "\t" '$3 ~ /^[0-9]+$/ {s += $3} END {print s + 0}' "$local_manifest")"
printf "remote lines: %s\n" "$(awk -F "\t" '$3 ~ /^[0-9]+$/ {s += $3} END {print s + 0}' "$remote_manifest")"

echo
echo "== Missing on remote =="
comm -23 "$local_paths" "$remote_paths" | head -80

echo
echo "== Extra on remote =="
comm -13 "$local_paths" "$remote_paths" | head -80

echo
echo "== Changed files =="
join -t $'\t' -j 4 \
  <(LC_ALL=C sort -t $'\t' -k4,4 "$local_manifest") \
  <(LC_ALL=C sort -t $'\t' -k4,4 "$remote_manifest") |
  awk -F "\t" '$2 != $5 {print $1}' |
  head -120

echo
echo "== Lines by top-level dir: local =="
awk -F "\t" '
  $3 ~ /^[0-9]+$/ {
    split($4, p, "/");
    key = p[1];
    files[key] += 1;
    lines[key] += $3;
  }
  END {
    for (key in lines) printf "%8d lines  %5d files  %s\n", lines[key], files[key], key;
  }
' "$local_manifest" | sort -nr

echo
echo "== Lines by top-level dir: remote =="
awk -F "\t" '
  $3 ~ /^[0-9]+$/ {
    split($4, p, "/");
    key = p[1];
    files[key] += 1;
    lines[key] += $3;
  }
  END {
    for (key in lines) printf "%8d lines  %5d files  %s\n", lines[key], files[key], key;
  }
' "$remote_manifest" | sort -nr

echo
echo "Manifest files:"
printf "  %s\n" "$local_manifest" "$remote_manifest"
