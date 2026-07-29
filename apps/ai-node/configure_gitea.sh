#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="${STACK_DIR:-$HOME/homecontrol-ai-node}"
GITEA_DATA_DIR="${GITEA_DATA_DIR:-/mnt/hc-backup/gitea}"
GITEA_URL="${GITEA_URL:-http://192.168.1.2:3002/}"
GITEA_DOMAIN="${GITEA_DOMAIN:-192.168.1.2}"
GITEA_SSH_PORT="${GITEA_SSH_PORT:-2222}"
GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-a}"
GITEA_ADMIN_EMAIL="${GITEA_ADMIN_EMAIL:-a@homecontrol.local}"
GITEA_ORG="${GITEA_ORG:-homecontrol}"
GITEA_REPO="${GITEA_REPO:-config}"
ADMIN_PASSWORD_FILE="${ADMIN_PASSWORD_FILE:-$GITEA_DATA_DIR/gitea-admin-password.txt}"
APP_INI="$GITEA_DATA_DIR/gitea/conf/app.ini"

cd "$STACK_DIR"

if [ ! -f "$APP_INI" ]; then
  docker compose --profile git up -d gitea
  sleep 5
fi

install -d -m 750 "$GITEA_DATA_DIR"
if [ ! -f "$ADMIN_PASSWORD_FILE" ]; then
  umask 077
  openssl rand -base64 24 > "$ADMIN_PASSWORD_FILE"
fi
chmod 600 "$ADMIN_PASSWORD_FILE"

SECRET_KEY="$(openssl rand -hex 32)"
INTERNAL_TOKEN="$(openssl rand -base64 48)"
cp "$APP_INI" "$APP_INI.bak.$(date +%Y%m%d-%H%M%S)"

python3 - "$APP_INI" "$GITEA_URL" "$GITEA_DOMAIN" "$GITEA_SSH_PORT" "$SECRET_KEY" "$INTERNAL_TOKEN" <<'PY'
import sys
from pathlib import Path

path, root_url, domain, ssh_port, secret_key, internal_token = sys.argv[1:]
ini = Path(path)
lines = ini.read_text(encoding="utf-8").splitlines()

sections = {}
current = ""
for index, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        current = stripped[1:-1]
        sections.setdefault(current, [])
    sections.setdefault(current, []).append(index)

def ensure_section(section):
    global lines
    if section in sections:
        return
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"[{section}]")
    sections[section] = [len(lines) - 1]

def set_value(section, key, value, only_if_empty=False):
    ensure_section(section)
    indexes = sections[section]
    start = indexes[0] + 1
    end = len(lines)
    for idx in range(start, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = idx
            break
    for idx in range(start, end):
        stripped = lines[idx].strip()
        if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
            _, _, current_value = lines[idx].partition("=")
            if only_if_empty and current_value.strip():
                return
            lines[idx] = f"{key} = {value}"
            return
    lines.insert(end, f"{key} = {value}")
    for name, idxs in sections.items():
        sections[name] = [idx + 1 if idx >= end else idx for idx in idxs]

set_value("server", "DOMAIN", domain)
set_value("server", "SSH_DOMAIN", domain)
set_value("server", "ROOT_URL", root_url)
set_value("server", "SSH_PORT", ssh_port)
set_value("server", "SSH_LISTEN_PORT", "22")
set_value("server", "DISABLE_SSH", "false")

set_value("database", "DB_TYPE", "sqlite3")
set_value("database", "PATH", "/data/gitea/gitea.db")

set_value("security", "INSTALL_LOCK", "true")
set_value("security", "SECRET_KEY", secret_key, only_if_empty=True)
set_value("security", "INTERNAL_TOKEN", internal_token, only_if_empty=True)

set_value("service", "DISABLE_REGISTRATION", "true")
set_value("service", "REQUIRE_SIGNIN_VIEW", "false")

ini.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

docker compose --profile git restart gitea
sleep 8

if ! docker exec -u git homecontrol-ai-gitea gitea admin user list --config /data/gitea/conf/app.ini | awk '{print $2}' | grep -qx "$GITEA_ADMIN_USER"; then
  docker exec -u git homecontrol-ai-gitea gitea admin user create \
    --config /data/gitea/conf/app.ini \
    --username "$GITEA_ADMIN_USER" \
    --password "$(cat "$ADMIN_PASSWORD_FILE")" \
    --email "$GITEA_ADMIN_EMAIL" \
    --admin \
    --must-change-password=false
fi

docker exec -u git homecontrol-ai-gitea gitea admin user list --config /data/gitea/conf/app.ini

python3 - "$GITEA_URL" "$GITEA_ADMIN_USER" "$ADMIN_PASSWORD_FILE" "$GITEA_ORG" "$GITEA_REPO" <<'PY'
import base64
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base_url, username, password_file, org, repo = sys.argv[1:]
password = open(password_file, "r", encoding="utf-8").read().strip()
auth = base64.b64encode(f"{username}:{password}".encode()).decode()

def request(method, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if exc.code == 422:
            return exc.code, {"already_exists": True, "raw": raw}
        raise

request("POST", "/api/v1/orgs", {"username": org, "full_name": "HomeControl", "visibility": "private"})
status, result = request(
    "POST",
    f"/api/v1/orgs/{org}/repos",
    {
        "name": repo,
        "description": "HomeControl configuration, automations, scripts and compose files",
        "private": True,
        "auto_init": True,
        "default_branch": "main",
    },
)
print(f"Repository ready: {base_url.rstrip('/')}/{org}/{repo} status={status}")
PY

echo "Gitea configured at $GITEA_URL"
echo "Admin user: $GITEA_ADMIN_USER"
echo "Admin password file: $ADMIN_PASSWORD_FILE"
