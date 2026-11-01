#!/usr/bin/env bash
set -Eeuo pipefail

PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/etc/homecontrol/restic-password}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! command -v restic >/dev/null 2>&1; then
  apt-get update
  apt-get install -y restic
fi

install -d -m 700 "$(dirname "$PASSWORD_FILE")"

if [ ! -f "$PASSWORD_FILE" ]; then
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 48 > "$PASSWORD_FILE"
  else
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c 64 > "$PASSWORD_FILE"
    printf '\n' >> "$PASSWORD_FILE"
  fi
fi

chown root:root "$PASSWORD_FILE"
chmod 600 "$PASSWORD_FILE"

echo "Restic is installed."
echo "Password file is ready: $PASSWORD_FILE"
