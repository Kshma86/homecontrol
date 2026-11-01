#!/usr/bin/env bash
set -Eeuo pipefail
CODE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "$CODE_DIR/restore_smoke.py" "$@"
