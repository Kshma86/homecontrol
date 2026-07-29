#!/usr/bin/env bash
set -Eeuo pipefail

TITLE="${1:-HomeControl backup}"
MESSAGE="${2:-Backup event}"
BASE="${BASE:-/srv/docker/homecontrol}"
ENV_FILE="${HC_BACKUP_NOTIFY_ENV:-$BASE/infra/.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

if [ "${HA_BACKUP_NOTIFY_ENABLED:-false}" != "true" ]; then
  exit 0
fi

HA_URL="${HA_BACKUP_URL:-${HA_BASE_URL:-}}"
HA_TOKEN="${HA_BACKUP_TOKEN:-}"

[ -n "$HA_URL" ] || exit 0
[ -n "$HA_TOKEN" ] || exit 0

python3 - "$HA_URL" "$HA_TOKEN" "$TITLE" "$MESSAGE" <<'PY'
import json
import sys
from urllib.request import Request, urlopen

base_url, token, title, message = sys.argv[1:5]
url = base_url.rstrip("/") + "/api/services/persistent_notification/create"
payload = json.dumps({"title": title, "message": message}).encode("utf-8")
request = Request(
    url,
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
)
with urlopen(request, timeout=10) as response:
    response.read()
PY
