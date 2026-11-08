#!/usr/bin/env bash
# Installs the one-minute auto-update timer. Run once as root on the server:  bash /opt/eternal-realm/deploy/install-updater.sh
set -euo pipefail

cat > /etc/systemd/system/eternal-realm-update.service <<'EOF'
[Unit]
Description=Eternal Realm: pull and deploy new commits when GitHub tests are green

[Service]
Type=oneshot
User=erbot
WorkingDirectory=/opt/eternal-realm
ExecStart=/bin/bash /opt/eternal-realm/deploy/auto-update.sh
EOF

cat > /etc/systemd/system/eternal-realm-update.timer <<'EOF'
[Unit]
Description=Check for new Eternal Realm commits every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=10s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now eternal-realm-update.timer
systemctl list-timers eternal-realm-update.timer --no-pager
echo "Updater installed. Watch it with: journalctl -u eternal-realm-update -f"
