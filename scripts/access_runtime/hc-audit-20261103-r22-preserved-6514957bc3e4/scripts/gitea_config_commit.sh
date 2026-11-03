#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
MESSAGE="${1:-Manual HomeControl configuration snapshot}"

"$BASE/scripts/sync_config_to_gitea.sh" "$MESSAGE"
