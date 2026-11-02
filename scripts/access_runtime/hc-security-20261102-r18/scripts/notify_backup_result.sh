#!/usr/bin/env bash
set -Eeuo pipefail

TITLE="${1:-HomeControl backup}"
MESSAGE="${2:-Backup event}"
BASE="${BASE:-/srv/docker/homecontrol}"
ENV_FILE="${HC_BACKUP_NOTIFY_ENV:-$BASE/infra/.env}"

env_value() {
  local key="$1"
  local default="$2"
  python3 - "$ENV_FILE" "$key" "$default" <<'PY' 2>/dev/null || printf '%s\n' "$default"
import sys
from pathlib import Path

path, wanted, default = sys.argv[1:4]
value = default
try:
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, item = line.split("=", 1)
        if key.strip() != wanted:
            continue
        item = item.strip()
        if (item.startswith('"') and item.endswith('"')) or (item.startswith("'") and item.endswith("'")):
            item = item[1:-1]
        value = item
        break
except Exception:
    pass
print(value)
PY
}

HA_BACKUP_NOTIFY_ENABLED="${HA_BACKUP_NOTIFY_ENABLED:-$(env_value HA_BACKUP_NOTIFY_ENABLED false)}"
HA_BACKUP_URL="${HA_BACKUP_URL:-$(env_value HA_BACKUP_URL "")}"
HA_BASE_URL="${HA_BASE_URL:-$(env_value HA_BASE_URL "")}"
HA_BACKUP_TOKEN="${HA_BACKUP_TOKEN:-$(env_value HA_BACKUP_TOKEN "")}"

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
