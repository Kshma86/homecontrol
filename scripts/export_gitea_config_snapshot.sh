#!/usr/bin/env bash
set -Eeuo pipefail
BASE="${BASE:-/srv/docker/homecontrol}"
exec python3 "$BASE/scripts/export_config_snapshot.py" "$@"
