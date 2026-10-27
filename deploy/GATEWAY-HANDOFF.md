# Finish the hosted pilot with one VPN server

Status: the Render admin/API and Neon database are configured. The Android pilot uses the hosted API. No VPN VPS has been purchased or provisioned. This installer has been syntax checked, but has not run on a real server or passed physical-phone routing tests.

## Resource to obtain

Use one dedicated Ubuntu 24.04 LTS VPS with public IPv4, `/dev/net/tun`, root access and a provider that permits a customer VPN. A 1-vCPU, 1-GB machine is a starting point for a small test, not a measured customer capacity. Choose Frankfurt for proximity to the existing Neon database; per-packet remote database accounting makes database latency important. Do not add a second gateway to this pilot.

For example, DigitalOcean lists a Basic 1-GB/1-vCPU server at US$6/month with 1,000 GiB monthly transfer (checked 2026-10-27: https://www.digitalocean.com/pricing/droplets). Taxes, transfer overages and optional services can add charges. This is a planning option, not a purchase or hosting guarantee. Account creation, billing verification and any provider terms must be completed by the owner. No hosting credentials or payment information belong in GitHub or chat.

You also need a DNS hostname you control, such as `vpn.example.co.za`, with an A record pointing directly to that VPS IPv4. Do not use a CDN HTTP proxy or add a non-working AAAA record. This hostname will be the VPN server address and TLS SNI; it must match the certificate. This installer does not register a domain or create DNS records.

## Install after the server exists

1. Allow inbound TCP 80 for certificate issuance/renewal and TCP 8443 for the VPN. Restrict SSH to your management addresses. Do not expose the database or admin API on this VPS.
2. Transfer a reviewed copy of this private repository to the server using authenticated Git or SSH. Do not put GitHub tokens in shell commands, scripts or Git remotes.
3. From the project root, run:

   ```bash
   sudo bash deploy/install-gateway.sh vpn.example.co.za your-certificate-email@example.co.za
   ```

   Replace both example values. The script installs dependencies, prompts privately for the SAME pooled Neon connection used by Render, obtains a public certificate, installs restart/reboot services, and enables the project's forwarding/isolation rules. It saves the connection only in root-readable `/etc/top-private-plug/gateway.env`. It does not migrate or reset customer records. An existing credential file is preserved on reruns. Run only on the dedicated server: it changes its network configuration.

4. Check the running process, certificate, database access and listener:

   ```bash
   sudo systemctl status top-private-plug-gateway.service --no-pager
   sudo journalctl -u top-private-plug-gateway.service --since '10 minutes ago' --no-pager
   sudo ss -ltnp 'sport = :8443'
   openssl s_client -connect vpn.example.co.za:8443 -servername vpn.example.co.za -verify_hostname vpn.example.co.za -verify_return_error </dev/null
   ```

   A listening process or valid TLS certificate does not prove packet routing works. Keep the environment file and logs containing any sensitive values private. Certbot's timer renews the certificate; the gateway reloads it every 60 seconds for new handshakes. Port 80 must remain available for renewals.

5. In the admin website create a trial profile with this hostname, port **8443**, matching SNI and TLS 1.2 or 1.3. Configure the desired MTN/Telkom/Cell C profiles on the same actual gateway. Carrier labels do not supply SIM data or a carrier agreement.
6. Set `TPP_REMOTE_GATEWAY=1` in Render and redeploy to enable pilot connection attempts. Issue one 1-hour/100-MB trial. On an actual Android phone activate it and approve VPN permission. Confirm HTTPS browsing and a public IPv4 belonging to the VPS. Check admin usage increments and verify suspension, quota exhaustion, expiry and cross-device code rejection using the acceptance checklist in `deploy/README.md`.
7. If routing or enforcement fails, unset `TPP_REMOTE_GATEWAY` in Render and redeploy. Suspend test accounts and stop the gateway if necessary. Do not sell access until the tests pass. The pilot still needs independent transport review and capacity measurements before commercial release.

## Updates and recovery

Review the new checkout and rerun the installer to update the gateway. It stops the old process before copying code and preserves the database URL. A restart disconnects current clients, which must reconnect. The network service reapplies forwarding after reboot without flushing unrelated firewall chains. Certificate-renewal failures, database outages and unavailable TUN must be investigated before restoring access. Back up PostgreSQL independently; neither this installer nor VPS deletion removes the separate Neon database.

The hosted admin's private bootstrap password should be removed from Render only after the owner has successfully signed in. The saved password hash remains in PostgreSQL.
