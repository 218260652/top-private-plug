#!/usr/bin/env bash
# Run on a NEW, dedicated Ubuntu VPS, from a reviewed checkout of this project.
# This installs packages, obtains a certificate and changes forwarding/firewall rules.
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo 'Run with sudo on the dedicated VPN server.' >&2; exit 1; fi
if [ "$#" != 2 ]; then echo 'Usage: sudo bash deploy/install-gateway.sh vpn.your-domain.example owner@email.example' >&2; exit 1; fi
vpn_host="$1"
owner_email="$2"
if [[ ! "$vpn_host" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || [[ "$vpn_host" != *.* ]] || [[ "$vpn_host" == *..* ]]; then
  echo 'Use a lowercase DNS hostname pointing directly to this server.' >&2; exit 1
fi
if [[ "$owner_email" != *@*.* ]] || [[ "$owner_email" == *[[:space:]]* ]] || [[ "$owner_email" == -* ]]; then echo 'Supply your certificate contact email.' >&2; exit 1; fi
source /etc/os-release
if [ "$ID" != ubuntu ] || [[ "$VERSION_ID" != 22.04 && "$VERSION_ID" != 24.04 ]]; then echo 'Use Ubuntu 22.04 or 24.04 LTS.' >&2; exit 1; fi
if [ ! -c /dev/net/tun ]; then echo 'This server has no /dev/net/tun; a TUN-capable VPS is required.' >&2; exit 1; fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -f "$project_root/backend/gateway_main.py" ]; then echo 'Run from the complete project checkout.' >&2; exit 1; fi
umask 077
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv python3-pip iproute2 iptables certbot ca-certificates
install -d -m 700 /etc/top-private-plug
install -d -m 755 /opt/top-private-plug
# Stop an existing gateway before changing its code. No database records are reset.
systemctl stop top-private-plug-gateway.service 2>/dev/null || true
cp -R "$project_root/backend" /opt/top-private-plug/
install -m 644 "$project_root/requirements.lock" /opt/top-private-plug/requirements.lock
install -m 700 "$project_root/deploy/configure-network.sh" /opt/top-private-plug/configure-network.sh
python3 -m venv /opt/top-private-plug/venv
/opt/top-private-plug/venv/bin/pip install -r /opt/top-private-plug/requirements.lock
if [ ! -f /etc/top-private-plug/gateway.env ]; then
  # The owner enters this privately in the server terminal, never in chat or GitHub.
  python3 - <<'PY'
import getpass, json, os
from urllib.parse import urlsplit, parse_qs
dsn = getpass.getpass('Paste the SAME Neon pooled connection used by Render (hidden): ')
parts = urlsplit(dsn)
if parts.scheme not in ('postgres', 'postgresql') or not parts.hostname or any(ord(c) < 32 for c in dsn):
    raise SystemExit('Invalid PostgreSQL connection; no credentials saved.')
if parse_qs(parts.query).get('sslmode', [''])[0] not in ('require', 'verify-ca', 'verify-full'):
    raise SystemExit('Require TLS with sslmode=require or verify-full in the connection URL.')
with open('/etc/top-private-plug/gateway.env', 'x', encoding='utf-8') as output:
    os.chmod(output.name, 0o600)
    output.write('DATABASE_URL=' + json.dumps(dsn, ensure_ascii=False) + '\n')
PY
fi
# Standalone certificate issuance needs DNS already pointing here and inbound TCP 80.
certbot certonly --standalone --non-interactive --agree-tos --email "$owner_email" --cert-name "$vpn_host" -d "$vpn_host"
cat > /etc/systemd/system/top-private-plug-network.service <<'UNIT'
[Unit]
Description=Top private Plug forwarding and client isolation
Wants=network-online.target
After=network-online.target
Before=top-private-plug-gateway.service

[Service]
Type=oneshot
ExecStart=/bin/bash /opt/top-private-plug/configure-network.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/top-private-plug-gateway.service <<UNIT
[Unit]
Description=Top private Plug single VPN gateway
Requires=top-private-plug-network.service
After=network-online.target top-private-plug-network.service
StartLimitIntervalSec=300
StartLimitBurst=10

[Service]
Type=simple
WorkingDirectory=/opt/top-private-plug
EnvironmentFile=/etc/top-private-plug/gateway.env
Environment=TPP_TLS_CERT=/etc/letsencrypt/live/$vpn_host/fullchain.pem
Environment=TPP_TLS_KEY=/etc/letsencrypt/live/$vpn_host/privkey.pem
Environment=TPP_GATEWAY_PORT=8443 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ExecStart=/opt/top-private-plug/venv/bin/python -m backend.gateway_main
Restart=on-failure
RestartSec=15
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now certbot.timer
systemctl enable --now top-private-plug-network.service top-private-plug-gateway.service
systemctl is-active --quiet top-private-plug-gateway.service
printf 'Gateway process started for %s:8443. This does not verify internet routing.\n' "$vpn_host"
printf 'Allow TCP 8443 and 80 in the provider firewall. Keep SSH restricted to your management addresses.\n'
printf 'Complete deploy/GATEWAY-HANDOFF.md acceptance checks before enabling customer connections.\n'
