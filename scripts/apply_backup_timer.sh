#!/usr/bin/env bash
set -Eeuo pipefail

BASE="/srv/docker/homecontrol"
UNIT_SRC="$BASE/scripts/systemd/homecontrol-backup.service"
TIMER_SRC="$BASE/scripts/systemd/homecontrol-backup.timer"
AI_WEEKLY_UNIT_SRC="$BASE/scripts/systemd/homecontrol-ai-weekly-backup.service"
AI_WEEKLY_TIMER_SRC="$BASE/scripts/systemd/homecontrol-ai-weekly-backup.timer"
UNIT_DST="/etc/systemd/system/homecontrol-backup.service"
TIMER_DST="/etc/systemd/system/homecontrol-backup.timer"
AI_WEEKLY_UNIT_DST="/etc/systemd/system/homecontrol-ai-weekly-backup.service"
AI_WEEKLY_TIMER_DST="/etc/systemd/system/homecontrol-ai-weekly-backup.timer"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

install -m 0644 "$UNIT_SRC" "$UNIT_DST"
install -m 0644 "$TIMER_SRC" "$TIMER_DST"
install -m 0644 "$AI_WEEKLY_UNIT_SRC" "$AI_WEEKLY_UNIT_DST"
install -m 0644 "$AI_WEEKLY_TIMER_SRC" "$AI_WEEKLY_TIMER_DST"

systemctl daemon-reload
systemctl enable --now homecontrol-backup.timer
systemctl enable --now homecontrol-ai-weekly-backup.timer
systemctl restart homecontrol-backup.timer
systemctl restart homecontrol-ai-weekly-backup.timer
