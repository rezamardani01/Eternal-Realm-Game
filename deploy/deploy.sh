#!/usr/bin/env bash
# Runs on the server (as the erbot user) after every push to main: back up, update, restart.
set -euo pipefail

cd /opt/eternal-realm

echo ">> backup"
mkdir -p backups
if [ -f data/game.db ]; then
  sqlite3 data/game.db ".backup 'backups/pre-deploy-$(date +%Y%m%d-%H%M%S).db'"
  ls -1t backups/pre-deploy-*.db 2>/dev/null | tail -n +15 | xargs -r rm -f   # keep the last 14
fi

echo ">> update"
git fetch --quiet origin main
git reset --hard origin/main

echo ">> dependencies"
.venv/bin/pip install --quiet -r requirements.txt

echo ">> restart"
sudo /bin/systemctl restart eternal-realm
sleep 4
sudo /bin/systemctl is-active eternal-realm
echo ">> deployed $(git rev-parse --short HEAD)"
