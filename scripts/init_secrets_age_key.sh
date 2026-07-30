#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
KEY_FILE="${AGE_KEY_FILE:-$BASE/infra/ssh/homecontrol-secrets-age-key.txt}"
RECIPIENT_FILE="${AGE_RECIPIENT_FILE:-$BASE/secrets/age-recipient.txt}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if ! command -v age-keygen >/dev/null 2>&1; then
  fail "age-keygen nem talalhato. Telepites Ubuntu alatt: sudo apt install age"
fi

install -d -m 700 "$(dirname "$KEY_FILE")"
install -d -m 755 "$(dirname "$RECIPIENT_FILE")"

if [ ! -s "$KEY_FILE" ]; then
  umask 077
  age-keygen -o "$KEY_FILE"
fi

recipient="$(sed -n 's/^# public key: //p' "$KEY_FILE" | head -n 1)"
[ -n "$recipient" ] || fail "Nem talalhato public recipient a kulcsban: $KEY_FILE"

printf '%s\n' "$recipient" > "$RECIPIENT_FILE"
chmod 644 "$RECIPIENT_FILE"
chmod 600 "$KEY_FILE"

echo "Age identity private key: $KEY_FILE"
echo "Age public recipient:      $RECIPIENT_FILE"
echo
echo "FONTOS: a private key-t kulon is mentsd el jelszokezelobe vagy offline helyre."
echo "A public recipient mehet Git/Gitea-ba, a private key nem."
