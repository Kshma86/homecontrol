#!/usr/bin/env bash
set -Eeuo pipefail
BASE="/srv/docker/homecontrol"
exec /usr/bin/python3 "$BASE/scripts/backup_runner.py" --mode local
