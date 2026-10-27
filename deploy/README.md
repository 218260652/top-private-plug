# Deploy on a dedicated Linux VPS

This package does not include a VPS, bandwidth, domain, carrier agreement or live credentials. It does not provide free mobile data. Use a dedicated Linux VPS with a public IPv4 address, `/dev/net/tun`, Docker Compose, `iproute2`, `iptables`, and permission to forward traffic. A managed web-only hosting service is not enough for this gateway. Single-node only: do not run several copies against one database or start several workers.

## 1. DNS and firewall

Point `admin.your-domain.co.za` and `vpn.your-domain.co.za` at the VPS IPv4 address. Leave any HTTP CDN proxy disabled for the VPN hostname. Do not publish AAAA records unless that host actually serves IPv6. Open inbound TCP 80 and 443 for certificate issuance / admin HTTPS, and TCP 8443 for the TLS VPN. Restrict SSH to your own management addresses. Keep 8080 private. Your upstream provider must permit this use and supply the bandwidth.

## 2. Configure

From the project root:

```bash
cp deploy/.env.example deploy/.env
```

Edit the three example values to your real hostnames and email address. The admin profile uses VPN port **8443** because Caddy already uses 443 for HTTPS. To use another port, change `TPP_GATEWAY_PORT`, firewall rules, and all corresponding admin profiles together. A new host or SNI requires a valid certificate and a provisioned listener; changing the database does not create infrastructure.

## 3. Enable forwarding on the VPS

Read `deploy/configure-network.sh`, then run it on the dedicated VPS:

```bash
sudo bash deploy/configure-network.sh
```

The script enables IPv4 forwarding, NAT and isolated forwarding for the VPN's `10.77.0.0/16` pool. It does not flush your existing firewall. Persist the added iptables rules using your distribution's firewall tooling. Review compatibility with any existing Docker or host firewall rules before enabling customers. The container does not need `--privileged`.

## 4. Start HTTPS and gateway

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail 50
```

Caddy obtains certificates. The service may restart until the first VPN certificate exists. If it does not appear, check DNS, public ports 80/443 and ACME messages. The configured storage path assumes Caddy's Let's Encrypt ACME issuer. Confirm the actual certificate path if you change issuers. The backend reloads certificate files every 60 seconds for new handshakes. Active sessions retain their existing TLS connection.

## 5. Create your admin locally

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec service python -m backend.manage create-admin --username admin --mfa
```

Enter a unique password of at least 14 characters. Add the displayed MFA secret to your authenticator and save its recovery copy securely. There are **no default admin credentials**. Open `https://admin.your-domain.co.za/admin/`. To recover access with local server ownership, run the same command with `reset-admin`; this invalidates all admin sessions.

## 6. Add profiles and access codes

Create enabled profiles labelled MTN, Telkom and Cell C as needed, each pointing to your real gateway hostname and port 8443. Set SNI to the hostname covered by the gateway certificate. TLS certificate and hostname validation cannot be disabled. Prefer TLS 1.3 where supported; older phones may require TLS 1.2.

Create a trial first: 1 hour, 100 MB, assigned to your enabled test profile. Copy the code when it is shown; the database stores only its hash. Install the pilot APK, open Settings → Service address and enter `https://admin.your-domain.co.za`. Enter the trial code, approve Android's VPN permission, then connect. Your admin should see activation, expiry and server-side byte totals.

The edit dialog can change the total duration in hours from original activation, add renewal days, change total quota, suspend/resume, or release the device binding. Shortening the total duration can expire an active account immediately. A replacement device keeps the original activation and expiry. Deleted accounts are tombstoned and disabled; usage/audit data is retained for accounting. No paid payment gateway is included: you sell a code through your own payment process.

## 7. Required acceptance checks before customers

- On an actual phone verify DNS, HTTPS browsing, streaming and mobile-network transitions. Confirm its public IPv4 changes to the gateway address. Do not infer success from a connected label alone.
- Confirm IPv6 is blocked while connected; confirm normal networking resumes after manual disconnection. This pilot has no always-on mode or kill switch.
- Suspend and delete the connected test account from another device; traffic must stop. Test idle expiry without the client status API and a tiny quota. Enforcement checks each packet and idle sessions every second; this is an implementation interval, not a measured production guarantee.
- Redeem the same code on another phone: reject. Redeem again with the same device key: preserve expiry. Reinstall: require an admin device reset; preserve original activation and expiry.
- Edit / disable an active profile: close its old session, fetch updated version, reconnect with valid certificate. Test rollback by re-saving the previous settings.
- Test each named carrier with an ordinary internet connection and your actual infrastructure. No billing bypass, carrier data subsidy, zero rating or bandwidth supply is implemented.
- Run a sustained concurrency, packet-loss and battery test for your target customer count. Measure CPU, disk IOPS, throughput and TCP-over-TCP effects. Have the custom transport independently reviewed before a commercial release.

## Backups and recovery

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec service python -m backend.manage backup --output /data/backup.sqlite3
```

Protect backups as secrets: they contain device public keys, password verifiers, the MFA secret and account records. Use encrypted storage and test restoration. Stop the service before restoring a database. Keep TLS keys separate from source control. Gateways enforce quota from durable SQL before forwarding; a database failure closes the affected tunnel rather than granting unmetered service. Account totals include upload and download IP packet lengths, not SIM billing or TLS overhead. A packet charged just before a transport failure is not refunded; accounting is conservative.

## Local admin-only development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
python -m backend.manage create-admin
TPP_LOCAL_DEV=1 TPP_PUBLIC_ORIGIN=http://127.0.0.1:8080 python -m backend.app
```

Open `http://127.0.0.1:8080/admin/` on the same computer. Local HTTP mode is only for development on loopback; Android requires HTTPS. Without gateway certificates, `/v1/connect` returns 503 explicitly.
