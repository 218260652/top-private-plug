[![Checks and pilot APK](https://github.com/218260652/top-private-plug/actions/workflows/checks.yml/badge.svg)](https://github.com/218260652/top-private-plug/actions/workflows/checks.yml)

# Top private Plug — 0.1.1 pilot

An original Android VPN client, admin dashboard, account API, SQLite database and Linux TLS gateway. This is an installable **debug-signed pilot**, not a verified commercial VPN release. No live service is deployed and no default admin credentials are shipped.

## What is implemented

| Requirement | Implementation |
| --- | --- |
| Paid access | Presets for 7, 15 and 30 days; custom minutes/hours/days |
| Free trials | Admin sets the duration and data allowance; no hard-coded trial period |
| First activation | Durable, atomic activation timestamp; re-entry never restarts it |
| Codes | Random 160-bit codes, shown once, stored as hashes |
| Device binding | Android Keystore P-256 key and signed, single-use challenges |
| Data caps | Durable, atomic upload + download accounting before packet forwarding |
| Admin actions | Create, edit duration, edit total quota, renew, suspend/resume, delete, rebind device |
| Connection profiles | MTN/Telkom/Cell C labels, server, port, custom SNI, minimum TLS, version, enabled state |
| Profile updates | Fetched before connection; old sessions closed; reconnect required |
| Monitoring | Online status, byte totals, 1/6/24-hour traffic charts, audit events |
| Android UI | Activation, Home, Usage, Plans, Settings, original shield-and-plug icon |
| Admin security | Password hashing, optional TOTP MFA, HttpOnly session cookies, origin checks and rate limiting |
| Deployment | Docker, Caddy HTTPS, Linux TUN setup, forwarding/firewall script, backup command |

**The protocol is TPP/1, our own framed IP-over-TLS transport. It is not Xray, HA Tunnel, WireGuard or OpenVPN compatible.** It uses platform TLS and cryptography libraries rather than custom encryption. No proprietary code, private keys, credentials, server infrastructure or native libraries from the reference APKs are included. The existing APKs and screenshots informed the product requirements and visual direction.

## Use the Android pilot

1. Deploy your own service using [deploy/README.md](deploy/README.md).
2. Create your admin account on the server. Add an enabled connection profile pointing at the real TLS gateway.
3. Create a short trial with a small data allowance. Copy its access code privately.
4. Install `Top-private-Plug-0.1.1-pilot.apk` on Android 8.0 or newer.
5. Open Settings → Service address and set your admin/API HTTPS origin.
6. Enter the access code, choose an assigned carrier profile and approve Android's VPN connection dialog.
7. Verify real traffic and server enforcement using the deployment acceptance checks before selling access.

Without a deployed gateway and certificates, the app cannot provide connectivity. SNI selects the certificate/service hostname during TLS setup; the Linux gateway and its upstream connection supply bandwidth. Carrier names are selectable labels, not endorsements, tested compatibility claims, billing bypasses or free-data arrangements. No prices or payment-provider details were invented.

## Project map

- `android/app/src/main/`: native Java Android app, icon and manifest.
- `backend/store.py`: account, code, challenge, quota and session logic.
- `backend/gateway.py`: TLS framing, packet validation and Linux TUN forwarding.
- `backend/app.py`: HTTP API and dashboard hosting.
- `backend/static/`: responsive admin dashboard.
- `backend/manage.py`: admin bootstrap/reset and consistent database backups.
- `deploy/`: Docker Compose, HTTPS configuration and network setup.
- `tests/`: account, API and TLS integration tests.
- `docs/`: protocol, research provenance and verification status.

## Local tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
python -m unittest discover -s tests -v
```

The gateway integration tests use real TLS sockets with a **simulated** packet device. They do not prove Android-to-internet routing or production throughput.

## Build Android

Install JDK 17 and the official Android SDK `platforms;android-35` and `build-tools;35.0.0`.

```bash
python tools/build_android.py --sdk /absolute/path/to/android-sdk
```

The dependency-free builder compiles the native app, creates DEX bytecode, aligns the APK and verifies its debug signature. A conventional Android Gradle project is also included (AGP 8.7.3; use compatible Gradle 8.9). This environment used Eclipse ECJ 3.39.0 as its Java compiler because only a JRE was preinstalled; the builder supports `--ecj /path/to/ecj.jar`. ECJ and the Android SDK are build tools, not bundled in the source package or APK.

The pilot is debuggable and signed with a standard debug certificate. Create and securely back up your own release signing key for commercial distribution. A later release signed with a different certificate will require uninstalling this pilot; uninstalling removes its Keystore device key and requires admin rebind, preserving expiry.

## Practical limitations

- No VPS, real domain, upstream bandwidth or live carrier tests are included.
- IPv4 only; IPv6 is captured and blocked while connected. There is no always-on mode or kill switch. After disconnect or failure, Android returns to its normal network.
- TCP-over-TCP affects throughput under loss. SQL is committed for every packet for strict accounting; scalability and disk performance need measurement. Single gateway process / single SQLite database only.
- UI and TLS gateway code compile / pass local tests, but Android runtime, battery, roaming, real TUN/NAT routing, container startup and a browser visual review are not verified here.
- The admin is a separate website, not a privileged screen inside the customer APK. Credentials and server keys stay outside source control. Account deletion revokes access and hides the account; accounting/audit records remain as a tombstone.
- Custom transport needs independent security review and sustained load testing before commercial use. No production security or performance certification is claimed.

See [docs/VALIDATION.md](docs/VALIDATION.md) for exact verification evidence and outstanding work.

## WhatsApp purchases and top-ups

Buy and top-up buttons open a prefilled WhatsApp request to **+27 70 384 1868**. Customers choose 7, 15, 30 days or a custom data/duration request; no price is assumed. Existing customers include a non-secret account reference so the admin can search the dashboard and renew the correct account. Access codes, device keys and login tokens are never included. The customer reviews and sends the message. Opening WhatsApp does not confirm payment, redeem a code or change time/data. The admin arranges payment and issues a fresh device-bound code or renews the existing account after confirming payment.

## GitHub updates

This repository contains the customer app, admin website, API and Linux gateway. The current reviewed pilot is in `downloads/Top-private-Plug-0.1.1-pilot.apk`. Because the repository is private, its files are not a public customer download link.

After each push or pull request, GitHub Actions runs the backend tests and builds a debug pilot APK. Open **Actions → Checks and pilot APK → a successful run → Artifacts** to download a build. The workflow does not deploy the admin site or start a VPN server. Each CI run generates a temporary debug signing key, so CI APKs may require uninstalling a previous build; for reliable upgrades, configure an owner-controlled release signing key through GitHub Secrets in a future release workflow. Never commit signing keys, passwords, access codes, databases or customer records.

The actual admin website needs its Python backend and persistent database on a running host. GitHub Pages cannot run this Python API or the Linux TUN gateway. Follow `deploy/README.md` for the server deployment path.
