#!/usr/bin/env bash
set -Eeuo pipefail

AI_BACKUP_HOST="${AI_BACKUP_HOST:-192.168.1.2}"
AI_BACKUP_USER="${AI_BACKUP_USER:-a}"
AI_BACKUP_MOUNT="${AI_BACKUP_MOUNT:-/mnt/hc-backup}"
AI_BACKUP_SSH_KEY="${AI_BACKUP_SSH_KEY:-/srv/docker/homecontrol/infra/ssh/ai_node_key}"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [ -n "$AI_BACKUP_SSH_KEY" ] && [ -f "$AI_BACKUP_SSH_KEY" ]; then
  SSH_OPTS=(-i "$AI_BACKUP_SSH_KEY" "${SSH_OPTS[@]}")
fi

REMOTE="${AI_BACKUP_USER}@${AI_BACKUP_HOST}"
TEST_FILE="${AI_BACKUP_MOUNT}/hc-write-test-$(date +%Y%m%d-%H%M%S)"

echo "Checking AI backup target: ${REMOTE}:${AI_BACKUP_MOUNT}"

ssh "${SSH_OPTS[@]}" "$REMOTE" "
  set -e
  findmnt '${AI_BACKUP_MOUNT}' >/dev/null
  test -w '${AI_BACKUP_MOUNT}'
  mkdir -p \
    '${AI_BACKUP_MOUNT}/database' \
    '${AI_BACKUP_MOUNT}/config' \
    '${AI_BACKUP_MOUNT}/files' \
    '${AI_BACKUP_MOUNT}/restic/homecontrol' \
    '${AI_BACKUP_MOUNT}/gitea'
  touch '${TEST_FILE}'
  ls -ld '${AI_BACKUP_MOUNT}' '${AI_BACKUP_MOUNT}/restic' '${AI_BACKUP_MOUNT}/restic/homecontrol'
  rm -f '${TEST_FILE}'
"

echo "AI backup target is writable and prepared."
