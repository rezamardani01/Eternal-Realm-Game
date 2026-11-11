#!/usr/bin/env bash
# One-time setup of the Bale mini app on the server. Run as root with the domain that points at this server:
#   sudo bash /opt/eternal-realm/deploy/setup-miniapp.sh play.example.com          # Caddy gets the HTTPS certificate
#   sudo bash /opt/eternal-realm/deploy/setup-miniapp.sh play.example.com cdn      # a CDN (e.g. ArvanCloud) does HTTPS
# Use "cdn" on servers in Iran: certificate authorities abroad cannot reach them, so the CDN's edge terminates
# HTTPS and talks to this server over plain HTTP on port 80.
# It installs Caddy, sends that domain to the bot's mini app on 127.0.0.1:8085, turns the mini app on in
# config.toml and restarts the bot. After that the bot's main menu shows «باز کردن مینی اپ».
set -euo pipefail

DOMAIN="${1:-}"
MODE="${2:-}"
APP_DIR="/opt/eternal-realm"
PORT=8085

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (sudo bash setup-miniapp.sh your.domain)"; exit 1
fi
if [ -z "${DOMAIN}" ]; then
  echo "Usage: sudo bash setup-miniapp.sh your.domain   (the domain's DNS A record must point at this server)"; exit 1
fi

echo ">> Caddy (HTTPS reverse proxy)"
if ! command -v caddy >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi
if [ "${MODE}" = "cdn" ]; then
  SITE="http://${DOMAIN}"   # the CDN does HTTPS; here plain HTTP, no certificate requests
else
  SITE="${DOMAIN}"
fi
cat > /etc/caddy/Caddyfile <<EOF
${SITE} {
	encode gzip
	reverse_proxy 127.0.0.1:${PORT}
}
EOF
systemctl enable --now caddy
systemctl reload caddy

echo ">> config.toml: [miniapp]"
CONFIG="${APP_DIR}/config.toml"
python3 - "$CONFIG" "$DOMAIN" "$PORT" <<'PY'
import re, sys
path, domain, port = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
block = f'[miniapp]\nenabled = true\nhost = "127.0.0.1"\nport = {port}\nurl = "https://{domain}"\n'
if re.search(r"^\[miniapp\]", text, flags=re.M):
    text = re.sub(r"^\[miniapp\][^\[]*", block + "\n", text, flags=re.M)
else:
    text = text.rstrip() + "\n\n" + block
open(path, "w", encoding="utf-8").write(text)
PY

echo ">> firewall (if ufw is on): open 80 and 443 for HTTPS"
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp
  ufw allow 443/tcp
fi

systemctl restart eternal-realm
sleep 4
systemctl is-active eternal-realm
echo ">> Done. The mini app is at https://${DOMAIN} and the bot's main menu shows «باز کردن مینی اپ»."
echo "   In @botfather you can also set the bot's main mini app to the same address."
