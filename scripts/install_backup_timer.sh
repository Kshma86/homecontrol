#!/usr/bin/env bash
set -Eeuo pipefail

BASE="/srv/docker/homecontrol"
APPLY_SCRIPT="$BASE/scripts/apply_backup_timer.sh"
APPLY_SERVICE_SRC="$BASE/scripts/systemd/homecontrol-backup-apply.service"
APPLY_PATH_SRC="$BASE/scripts/systemd/homecontrol-backup-apply.path"
APPLY_SERVICE_DST="/etc/systemd/system/homecontrol-backup-apply.service"
APPLY_PATH_DST="/etc/systemd/system/homecontrol-backup-apply.path"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

chmod 0755 "$APPLY_SCRIPT"
install -m 0644 "$APPLY_SERVICE_SRC" "$APPLY_SERVICE_DST"
install -m 0644 "$APPLY_PATH_SRC" "$APPLY_PATH_DST"

"$APPLY_SCRIPT"
systemctl enable --now homecontrol-backup-apply.path
systemctl restart homecontrol-backup-apply.path
systemctl status homecontrol-backup.timer --no-pager
systemctl status homecontrol-backup-apply.path --no-pager
