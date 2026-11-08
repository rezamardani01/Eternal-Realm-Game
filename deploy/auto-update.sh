#!/usr/bin/env bash
# Runs on the server every minute (systemd timer). It asks GitHub whether main moved, and if the tests
# passed for the new commit it runs deploy.sh. No inbound connection to the server is needed.
set -euo pipefail

cd /opt/eternal-realm
REPO="rezamardani01/Eternal-Realm-Game"

git fetch --quiet origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0

# only deploy a commit whose GitHub tests finished green
STATE=$(curl -fsS --max-time 20 "https://api.github.com/repos/${REPO}/commits/${REMOTE}/check-runs" \
  | python3 -c 'import json,sys; runs=json.load(sys.stdin)["check_runs"]; t=[r for r in runs if r["name"]=="test"]; print(t[0]["conclusion"] or "pending" if t else "none")' || echo unknown)

case "$STATE" in
  success) echo "tests green for ${REMOTE:0:7}: deploying"; bash deploy/deploy.sh ;;
  failure) echo "tests failed for ${REMOTE:0:7}: not deploying" ;;
  *)       echo "tests for ${REMOTE:0:7} not finished yet (${STATE}): waiting" ;;
esac
