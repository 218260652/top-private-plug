# Hosted admin website

The hosted admin/API uses a free Render Python service in the owner's confirmed **My Workspace**, with a separate PostgreSQL database in the owner's free Neon organization. This avoids storing customer records on Render's temporary filesystem. No other app's database or service is reused.

The service is linked to this repository's `main` branch. Its build command is `pip install -r requirements.lock`; its start command is `python -m backend.hosted`. Before starting HTTP, that command runs the entitlement regression suite against an isolated PostgreSQL schema, removes only that test schema, and applies the public schema using the direct connection. Runtime requests use a pooled connection.

## First login: choose your password privately

If database credentials have not been configured, the hosted site serves a read-only setup guide. The owner must copy the pooled connection into `DATABASE_URL` and the direct connection into `TPP_MIGRATION_URL` using Render's private Environment settings. No credentials are accepted through that public page, and all account/API writes return 503 until configuration is complete.

1. Open this service in the Render Dashboard and select **Environment**.
2. Add `TPP_BOOTSTRAP_PASSWORD` with a unique password of at least 14 characters. Enter it in Render, not in chat or GitHub.
3. Save and redeploy. On first startup only, the app creates username **admin** with a hashed password in PostgreSQL.
4. Open the admin website and sign in as **admin** using that password.
5. After successful sign-in, remove `TPP_BOOTSTRAP_PASSWORD` from Render's environment and redeploy. The database retains the admin login. A normal redeploy never resets the password or customer accounts.

There is no default password and no public registration endpoint. Until the owner sets this secret, account-management operations remain unavailable to visitors. CLI `backend.manage` also supports PostgreSQL via `DATABASE_URL`, including admin reset and MFA setup. Use `pg_dump` with securely stored credentials for PostgreSQL backups.

## Environment variables

| Name | Purpose |
| --- | --- |
| `DATABASE_URL` | Secret pooled PostgreSQL connection for application traffic |
| `TPP_MIGRATION_URL` | Secret direct PostgreSQL connection for migration and isolated regression checks |
| `TPP_BOOTSTRAP_PASSWORD` | Owner-entered initial password; remove after first setup |
| `TPP_PUBLIC_ORIGIN` | Optional custom HTTPS origin; otherwise uses Render's documented `RENDER_EXTERNAL_URL` |
| `TPP_HTTP_BIND` | `0.0.0.0` on Render |
| `PORT` | Render's supplied HTTP listening port |
| `TPP_REMOTE_GATEWAY` | Leave unset until the separate Linux VPN gateway is provisioned and verified |

Do not commit credential values. Free tiers have resource limits and may sleep; they are for the pilot, not a commercial availability guarantee. Database persistence is independent of the Render instance, but account records still require backups and operational monitoring.

## VPN gateway is separate

For the current Render + Neon setup, use the dedicated-server installer and owner checklist in [`deploy/GATEWAY-HANDOFF.md`](../deploy/GATEWAY-HANDOFF.md). It provides a systemd service, reboot forwarding and certificate renewal, but no VPS has yet been provisioned or tested.

The website manages accounts; it does not supply VPN bandwidth. A Linux host with TUN, NAT, an owned certificate and upstream bandwidth is still required. On that host:

1. Install the project and its locked Python dependencies.
2. Configure forwarding/isolation using `deploy/configure-network.sh` after reviewing it for that host.
3. Securely configure `DATABASE_URL` for the SAME database, plus `TPP_TLS_CERT`, `TPP_TLS_KEY` and `TPP_GATEWAY_PORT`.
4. Run a single `python -m backend.gateway_main` process under a service supervisor.
5. Create admin connection profiles for that actual host, port and certificate hostname.
6. Enable `TPP_REMOTE_GATEWAY=1` on the admin service only after the gateway is operational. Test expiry, quotas, suspension and actual internet routing on a physical Android device.

Web-only restarts preserve active gateway session records. A gateway restart clears stale tunnel sessions. Do not run several packet gateways concurrently in this pilot. Strict database accounting over the network adds latency; capacity must be measured and the transport reviewed before selling access.

## Hosting created

- Admin/setup URL: https://top-private-plug-admin.onrender.com/admin/
- Owner environment settings: https://dashboard.render.com/web/srv-dbggmc61egvs73a84s8g/env
- Service is free, in Frankfurt, linked to the private GitHub repository with automatic deploys.
- Deployment was created WITHOUT database credentials. The owner subsequently entered the connection strings privately in Render; verification below confirms the operational admin dashboard.

## Owner setup verified

The owner completed runtime database configuration. The latest deployment reports live, 26 PostgreSQL entitlement tests passed, `/health` returns `status: ok` with `gateway_enabled: false`, and `/setup-status` returns `setup_required: false`. The admin login exists. Login was not attempted with the owner’s private password. The gateway still needs a separately provisioned Linux server and end-to-end acceptance testing.
