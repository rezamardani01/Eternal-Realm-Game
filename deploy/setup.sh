#!/usr/bin/env bash
# One-time server setup for Eternal Realm (Ubuntu/Debian). Run as root:
#   curl -fsSL https://raw.githubusercontent.com/rezamardani01/Eternal-Realm-Game/main/deploy/setup.sh -o setup.sh && sudo bash setup.sh
# It asks for the bot token and owner id; nothing secret is stored in the repository.
set -euo pipefail

REPO="https://github.com/rezamardani01/Eternal-Realm-Game.git"
APP_USER="erbot"
APP_DIR="/opt/eternal-realm"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (sudo bash setup.sh)"; exit 1
fi

echo ">> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git sqlite3 software-properties-common curl

# the bot needs Python 3.11 or newer
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo ">> Installing Python 3.12"
  apt-get install -y python3.12 python3.12-venv || { add-apt-repository -y ppa:deadsnakes/ppa && apt-get update -y && apt-get install -y python3.12 python3.12-venv; }
  PY="python3.12"
fi
apt-get install -y python3-venv python3-pip || true
echo ">> Using $($PY --version)"

echo ">> Creating the service user ${APP_USER}"
id -u "${APP_USER}" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "${APP_USER}"

echo ">> Fetching the code into ${APP_DIR}"
if [ ! -d "${APP_DIR}/.git" ]; then
  git clone "${REPO}" "${APP_DIR}"
fi
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo ">> Python environment"
# Slow or filtered networks: no pip self-upgrade, long timeouts, many retries. Set PIP_INDEX_URL to use a mirror.
PIP_ARGS="--default-timeout=120 --retries 10 ${PIP_INDEX_URL:+-i ${PIP_INDEX_URL}}"
sudo -u "${APP_USER}" bash -c "cd ${APP_DIR} && { [ -d .venv ] || ${PY} -m venv .venv; } && { .venv/bin/python -c 'import baleropy, aiosqlite' 2>/dev/null || .venv/bin/pip install ${PIP_ARGS} -r requirements.txt; }"

if [ ! -f "${APP_DIR}/config.toml" ]; then
  echo ">> Bot settings (typed here, saved only on this server)"
  read -r -p "Bot token (from @botfather in Bale): " TOKEN
  read -r -p "Owner numeric id: " OWNER
  read -r -p "Payment provider token [WALLET-TEST-1111111111111111]: " PROVIDER
  PROVIDER="${PROVIDER:-WALLET-TEST-1111111111111111}"
  cat > "${APP_DIR}/config.toml" <<EOF
[bot]
token = "${TOKEN}"
owner_id = ${OWNER}
admin_ids = []

[database]
path = "data/game.db"

[payments]
enabled = true
provider_token = "${PROVIDER}"
EOF
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/config.toml"
  chmod 600 "${APP_DIR}/config.toml"
fi

echo ">> systemd service"
cp "${APP_DIR}/deploy/eternal-realm.service" /etc/systemd/system/eternal-realm.service
systemctl daemon-reload
systemctl enable --now eternal-realm

echo ">> Letting ${APP_USER} restart only this service (needed by automatic deploys)"
cat > /etc/sudoers.d/eternal-realm <<EOF
${APP_USER} ALL=(root) NOPASSWD: /bin/systemctl restart eternal-realm, /bin/systemctl is-active eternal-realm
EOF
chmod 440 /etc/sudoers.d/eternal-realm

echo ">> Deploy key for GitHub Actions"
KEY="/home/${APP_USER}/.ssh/deploy_key"
sudo -u "${APP_USER}" mkdir -p "/home/${APP_USER}/.ssh"
if [ ! -f "${KEY}" ]; then
  sudo -u "${APP_USER}" ssh-keygen -t ed25519 -N "" -C "github-deploy" -f "${KEY}" >/dev/null
  cat "${KEY}.pub" >> "/home/${APP_USER}/.ssh/authorized_keys"
  chown "${APP_USER}:${APP_USER}" "/home/${APP_USER}/.ssh/authorized_keys"
  chmod 600 "/home/${APP_USER}/.ssh/authorized_keys"
fi

echo
echo "================ DONE ================"
systemctl --no-pager --lines=5 status eternal-realm || true
echo
echo "Now add these 3 secrets in GitHub (Settings > Secrets and variables > Actions):"
echo "  SERVER_HOST = this server's IP"
echo "  SERVER_USER = ${APP_USER}"
echo "  SERVER_SSH_KEY = the private key printed below (copy everything, including the BEGIN/END lines)"
echo "-------- PRIVATE KEY (keep secret) --------"
cat "${KEY}"
echo "-------------------------------------------"
