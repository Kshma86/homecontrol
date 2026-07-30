#!/usr/bin/env bash
set -Eeuo pipefail

BASE="${BASE:-/srv/docker/homecontrol}"
GITEA_REMOTE="${GITEA_REMOTE:-ssh://git@192.168.1.2:2222/homecontrol/config.git}"
GITEA_SSH_KEY="${GITEA_SSH_KEY:-$BASE/infra/ssh/ai_node_key}"
REF="${1:-main}"
TARGET="${2:-$BASE/restore_staging/gitea-config-$(date +%F_%H-%M-%S)}"

export GIT_SSH_COMMAND="ssh -i $GITEA_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

mkdir -p "$TARGET"
git clone "$GITEA_REMOTE" "$TARGET"
git -C "$TARGET" checkout "$REF"

cat <<EOF
== Gitea config restore staging kész ==
Ref: $REF
Target: $TARGET

Ez nem írt felül éles HC fájlt. Innen kézzel lehet összehasonlítani vagy visszamásolni.
Példa diff:
  diff -ru "$TARGET/scripts" "$BASE/scripts"
EOF
