# Customer account staging build

The development branch is `develop/customer-auth-staging`. It adds a customer API under `/v2/customer/` and a customer admin dashboard at `/admin/` on the isolated staging service. Existing profile import tools are at `/admin/legacy/` on staging. The production app ID and activation API remain available on their existing path.

## Deployment prerequisites

Use a separate Render service at `https://top-private-plug-test-api.onrender.com` and a separate PostgreSQL database named `top_private_plug_test_db`. Confirm that the hostname is under the owner’s Render workspace before using it. Use the supplied staging blueprint or set the same values in a dedicated service. The staging branch must remain separate from the production deployment.

Set `TPP_CUSTOMER_STAGING=1` to enable the customer API and admin. Set `DATABASE_URL` to the dedicated runtime connection and `TPP_MIGRATION_URL` to the dedicated migration connection. Both must refer to the staging database. Set a unique `TPP_BOOTSTRAP_PASSWORD` privately for initial administrator creation and remove it after use. The existing admin CLI can configure an alternate username and optional TOTP. Use fresh staging-only logins and test VPN credentials.

The additive migration is `backend/migrations/001_customer.sql`. Rehearse with isolated PostgreSQL. On rollback, disable `TPP_CUSTOMER_STAGING` and retain the new tables for recovery. Production account migration requires a verified backup, a separately rehearsed mapping of legacy entitlements, and explicit owner approval. This change does not migrate production customer rows.

## Install and test

Download and extract the signed test APK from the matching **Customer staging checks and test APK** run. Verify the APK using its supplied SHA-256 and metadata. The expected application ID is `za.co.topprivateplug.test`, label `Top Private Plug`, version `0.2.1`, and code `26`. Install alongside production with Android’s package installer or `adb install -r`. This signing identity differs from previous pilots, so an older test package signed with a different key may need to be uninstalled. Android allows only one active VPN at a time.

1. In the staging admin, create a customer with a temporary password and a short subscription.
2. Import a TLS-verified VLESS profile using staging credentials via the legacy profile import page. Assign it to a carrier on the customer dashboard.
3. In the test app, log in with the password supplied by the administrator. Close and reopen the app and verify session restore. Confirm the unconfigured networks are disabled.
4. Select a configured network, grant Android VPN permission, connect, and verify browser egress through the VPN. Disconnect and verify normal routing returns.
5. Repeat across Wi-Fi and approved mobile-data connections on each physical carrier. Set the carrier verification checkbox only after testing the current profile version.
6. Suspend the customer during a connection and verify the official client stops. Repeat for natural expiry and device revocation. Check that a new authorization is refused.
7. Verify the real gateway independently rejects a copied or previously issued credential and terminates already-open flows before claiming server-side revocation. This build implements an app-reported lease around legacy supplier imports, so that check requires a managed gateway integration.

## Current scope

Customer passwords are Argon2id-hashed. Staging uses short-lived opaque access tokens, device-proof-protected refresh rotation, server-side session/device revocation, and single-device leases with 30-second maximum heartbeat renewal. The admin provisions initial and reset passwords, customers change them on first login, and administrators can suspend, reactivate, permanently revoke, adjust expiry, manage plans, revoke devices and assign versioned profiles. Audit and activity are displayed. Gateway connections are shown as unavailable until measured server-side telemetry is integrated.

This staging increment still needs production customer migration, named admin roles, verified self-service recovery, upstream credential enforcement and telemetry, and physical device/carrier validation. Static supplier configuration is delivered to the authorized test client and must be treated as recoverable on a compromised phone. Keep these builds and credentials in staging.
