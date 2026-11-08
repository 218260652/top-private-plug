# Connectivity Fast Path 1.0 — Architecture and implementation gate

Status: design/implementation prerequisite; no runtime behavior changed by this document.

Target: make repeat VPN connection setup go directly from the Android client to the assigned VLESS endpoint after first activation, without an admin API roundtrip on the connection critical path.

## Current behavior verified in the parent branch

The current Android flow is not yet admin-free after activation:

1. Activation calls `/health`, `/v1/challenge`, and `/v1/activate`.
2. The app downloads assigned profiles from `/v1/profiles`.
3. `Api.prepareProfiles` obtains a profile bootstrap through `/v1/connect` and releases its temporary lease through `/v1/xray/disconnect`, then stores the encrypted profile bootstrap in Android app storage.
4. On a later connect, `TunnelService.runTunnel` can start the cached profile first, but still calls `Api.connect`. That call checks `/health`, requests a fresh `/v1/challenge`, and calls `/v1/connect` to obtain a new single-session lease.
5. While connected, `TunnelService.runXray` calls `/v1/xray/heartbeat` every five seconds. The heartbeat extends a 30-second lease and reports app-measured traffic for quota accounting.
6. `MainActivity.poll` can refresh account state every ten seconds.

Relevant source:
- `android/app/src/main/java/za/co/topprivateplug/Api.java`
- `android/app/src/main/java/za/co/topprivateplug/TunnelService.java`
- `android/app/src/main/java/za/co/topprivateplug/Vault.java`
- `backend/xray.py`
- `backend/store.py`

## Non-negotiable security constraint

Do not simply remove `/v1/connect`, heartbeats, or server-side expiry checks while continuing to use a shared imported upstream VLESS/Trojan credential.

The current backend returns a normalized imported outbound configuration and enforces account status, expiry, profile version, session exclusivity, and quota through short-lived leases and heartbeats. A locally cached shared upstream credential cannot independently enforce an individual customer's expiry, suspension, revocation, single-session policy, or quota. Client-side expiry checks alone are bypassable (modified APK, rooted device, clock changes, or extracted configuration).

Therefore, a direct-to-VLESS fast path is safe only when the actual VLESS endpoint can authenticate and enforce a unique per-account credential or equivalent server-verifiable grant.

## Target architecture

### A. First activation (admin control plane)

1. Android sends the activation code, selected network, and device-key proof over HTTPS.
2. Admin verifies code state, expiry, quota, suspension, device binding, and assigned network/profile.
3. Admin provisions or obtains a unique customer credential at a managed VLESS endpoint. The endpoint must enforce account expiry/revocation and, where required, quota/session limits.
4. Admin returns the assigned endpoint, unique credential, profile version, network binding, and a signed entitlement/credential metadata envelope.
5. Android validates the signed response and stores the credential using Android Keystore-backed encryption. Never store the activation code as a VLESS password.

### B. Normal connection (data plane)

1. User presses Connect.
2. Android loads the selected network's locally stored profile and unique credential.
3. Android starts Xray and connects directly to the assigned VLESS endpoint.
4. The VLESS endpoint authenticates the unique credential and enforces expiry/revocation/quota/session policy.
5. No admin API request is made on the connection critical path or during routine tunnel keepalive.
6. Admin API is used for activation, renewal, explicit account refresh, profile changes, and recovery—not every connect.

### C. Admin and endpoint enforcement

The admin must be able to provision, rotate, suspend, revoke, and expire each customer's credential at the VLESS endpoint. Quota must be enforced at the endpoint or by a trusted gateway-side accounting mechanism, not solely from client-reported counters. Revocation latency and maximum offline exposure must be explicit and tested.

## Required capability decision before coding the data-plane bypass

Confirm that the deployed VLESS endpoint is controlled by this project or exposes a documented authenticated provisioning API that can:
- create unique credentials per account/device as required;
- set expiry or revoke credentials server-side;
- disable credentials immediately on suspension/deletion;
- enforce or reliably account for data quota;
- enforce concurrency/session limits if the product promises them;
- report credential state safely to the admin backend.

If the endpoint is a third-party imported server and provides no provisioning/revocation API, this fast path cannot safely replace the existing lease model. Keep the current flow for that profile and do not ship an insecure offline bypass.

## Rollout strategy

Use a capability-gated migration:
- `managed_unique_credentials`: direct fast path only for profiles whose endpoint supports all required enforcement.
- Existing imported/shared profiles: retain the current lease + heartbeat path.
- Do not silently switch a customer's existing profile mode.
- Keep the current path as a rollback option until physical carrier testing is complete.

## Acceptance tests

### Android/API behavior
- First activation verifies with admin and persists the assigned network-bound credential.
- Subsequent connect on a managed profile makes zero requests to `/health`, `/v1/challenge`, `/v1/connect`, or heartbeat endpoints.
- App restart and process death still connect using the protected saved credential.
- Switching MTN/Telkom/Cell C selects only the matching credential slot.
- Logout clears the credential and cached profile for that network.
- Credential rotation/profile version changes invalidate stale cache safely.
- Existing legacy/shared profiles continue using the lease path.

### Server enforcement
- Expired, suspended, deleted, revoked, and quota-exhausted credentials are rejected by the VLESS endpoint even if the Android client is modified or its clock is changed.
- Cross-network credential reuse is rejected.
- Concurrent session policy is enforced at the server.
- Revocation propagation has a measured upper bound.
- Usage accounting cannot be forged by client-reported counters.

### Performance and field validation
- Measure activation duration separately from tunnel startup.
- Measure connect-button-to-tunnel-ready p50/p95 on Wi-Fi and each physical carrier.
- Test MTN, Telkom, and Cell C SIMs separately, including reconnect, network switching, screen-off, data usage, expiry, and suspension.
- Emulator success is automated verification only; it does not count as physical carrier validation.

## Safety boundary

This branch is a draft only. Do not merge, deploy, publish, change production configuration, or modify customer accounts without explicit owner approval.
