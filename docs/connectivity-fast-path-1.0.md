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


## Supplied MTN/Telkom profile review (2026-11-08)

The owner supplied one VLESS JSON profile described as being used for MTN and Telkom. It contains:
- an external hostname, `smraiyyan.com`, on TCP port `8446`;
- VLESS over TLS with WebSocket transport settings;
- a UUID credential;
- a chained HTTP proxy outbound and a proxy identity header;
- TLS `allowInsecure: true`.

This is evidence of an imported third-party endpoint, not evidence that Top Private Plug owns or administers the VLESS server. The supplied message contains only one JSON profile, so separate MTN and Telkom endpoint/credential assignments have not yet been verified.

Security and implementation consequences:
- Do not assume the UUID is unique to a Top Private Plug customer. Its per-customer scope and provider-side revocation semantics are unknown.
- Do not put the supplied UUID, proxy identity header, or other credential material in source control, CI logs, issue text, or screenshots. Treat the pasted credential as exposed; if it is active and grants access, ask the provider to rotate it and provision a replacement securely.
- `allowInsecure: true` disables normal TLS certificate validation and permits interception by an active network attacker. Before production use, verify the provider's certificate chain and hostname, then set certificate verification to strict. Do not silently change this in the app until compatibility has been tested against the actual endpoint.
- The profile's chained HTTP proxy and headers may be required for the carrier-specific route. Preserve them during refactoring until each carrier has been physically tested; do not simplify the outbound chain based only on emulator results.
- The endpoint's management API, per-user credential provisioning, server-side expiry, revocation, quota accounting, and concurrency controls remain unknown.

Decision: keep the existing lease/heartbeat enforcement for this imported profile until the provider confirms and demonstrates per-customer credential provisioning and server-side revocation/expiry/quota enforcement. The direct no-admin-roundtrip path can be enabled only for a separately verified managed endpoint capability. No runtime code change is authorized by this profile review.


## 3X-UI provider-panel discovery (2026-11-08)

The owner confirmed that the VLESS provider panel is 3X-UI. The upstream 3X-UI project documents a REST API and an in-panel OpenAPI document at `/panel/api/openapi.json`. Its current API reference describes client creation, update, enable/disable, traffic inspection, and expiry/quota-related client fields. API tokens created in Settings are full-admin credentials.

This makes 3X-UI a plausible provisioning/control-plane integration, but it does not yet prove that this deployment can safely replace the current lease path. The deployed panel version, base path, inbound ID/protocol/transport, API feature set, and provider-side enforcement behavior must be checked against the live panel's own API Docs/OpenAPI schema.

Integration security requirements:
- The Android app must never call 3X-UI directly and must never contain the panel API token.
- Store the full-admin API token only in the Top Private Plug backend's secret manager/environment, with restricted access, rotation, and redaction from logs.
- The backend must map each Top Private Plug account to a distinct 3X-UI client identity (UUID/client ID) and the intended inbound(s); never distribute a shared provider credential to multiple customers if individual suspension/revocation is promised.
- Provision, update, disable, and revoke through the documented API for the exact deployed version. Verify that expiry and traffic quota are enforced by the running Xray service, not merely displayed in the panel.
- Confirm how the panel handles exhausted quota, expired clients, resets, traffic accounting, and concurrent connections. Do not assume the UI's displayed counters are a hard real-time quota gate.
- Keep API access server-side. Do not expose panel URL, API token, admin password, client UUIDs, or customer identifiers in the Android APK, public repository, CI output, or screenshots.
- Test on a dedicated non-production inbound/client first. Do not modify existing provider clients or inbounds during discovery.

Next evidence required from the owner (redacted screenshots/text only):
1. 3X-UI version/build shown in the panel.
2. The inbound details for the MTN/Telkom profile: protocol, transport, TLS/Reality mode, and inbound ID/remark. Redact hostnames, UUIDs, private keys, passwords, subscription URLs, and tokens.
3. Whether API Docs is visible and whether the live OpenAPI page loads. Do not send the API token or admin login.
4. Confirmation that the owner is authorized to create and revoke test clients on a dedicated test inbound.

Until these checks pass, keep the current imported-profile lease/heartbeat behavior. The 3X-UI discovery does not authorize runtime bypass, provider-side changes, or production credential modifications.


## 3X-UI inbound details reported by owner (2026-11-08)

The owner inspected an inbound labelled `Vless` and reported:
- protocol: VLESS;
- transport: TCP;
- security: TLS;
- port: 40757;
- clients: 1;
- traffic: 44.57 GB / unlimited;
- duration: infinity.

Interpretation and unresolved points:
- The reported client currently has no expiry configured and no traffic cap configured. This is not sufficient evidence of per-customer subscription enforcement.
- The inbound reports one client. This does not establish whether the imported profile UUID previously supplied is that client; compare locally in the panel without sending or committing the UUID.
- The reported inbound uses TCP+TLS on port 40757, while the supplied imported client profile previously described VLESS over WebSocket+TLS to an external hostname on port 8446, with a chained HTTP proxy. These do not obviously describe the same listener. Do not assume this inbound is the actual endpoint used by the app until the owner verifies the relationship locally.
- The inbound aggregate traffic figure must not be treated as a per-customer quota measurement.

Next implementation gate:
1. Verify whether this is the inbound that actually receives the app's VLESS connection.
2. On a dedicated test inbound, create a separate test client and verify that the panel/Xray enforce expiry, traffic cap, disable, and deletion/revocation at connection time.
3. Verify traffic accounting and reset semantics, including whether a quota-exhausted client is actually rejected by Xray.
4. Only then design backend provisioning against the exact deployed 3X-UI API version. Keep the existing admin lease/heartbeat path for current imported profiles until those tests pass.

No live inbound, client, port, TLS setting, or provider account has been modified.


## Second inbound clarified by owner (2026-11-08)

The owner clarified that the VLESS inbound described above is the second inbound shown in the dashboard. The first inbound, labelled `TR`, is reported as:
- protocol: Trojan;
- transport: TCP;
- security: TLS;
- port: 8446;
- clients: 1;
- traffic: 108.9 MB / unlimited;
- duration: infinity.

This confirms two distinct inbounds in the panel:
- `TR`: Trojan / TCP / TLS / port 8446;
- `Vless`: VLESS / TCP / TLS / port 40757.

Important reconciliation:
- The previously supplied app profile was described as a VLESS outbound to an external host on port 8446 using WebSocket+TLS and an HTTP proxy chain. That does not match the panel's `TR` inbound protocol/transport (Trojan over TCP+TLS), nor the panel's `Vless` inbound port (40757). There may be another provider endpoint, an intermediary/proxy, a mislabeled profile, or an inaccurate earlier description. Do not infer that the app profile maps to either inbound yet.
- Both inbounds show one client, unlimited traffic, and infinite duration. Those settings do not currently demonstrate customer-specific quota or expiry enforcement.
- Before integration, the owner must identify which inbound each carrier profile actually connects to. Compare the imported profile's protocol, host, port, transport, TLS server name and WS path locally against the inbound configuration. Do not share UUIDs, passwords, proxy identity headers, private keys, or tokens.
- Do not change either live inbound. Use a separate test inbound/client for any provisioning or enforcement experiments.


## Owner-confirmed client controls and official 3X-UI API review (2026-11-08)

The owner confirms the panel UI permits editing clients and exposes controls to add clients, set per-client traffic limits and expiry, and enable/disable clients. This is a useful prerequisite, but no test client has been created and no enforcement test has been performed.

The current upstream 3X-UI documentation describes:
- unique client email identifiers;
- UUID credentials for VLESS and passwords for Trojan;
- per-client traffic quota and expiry;
- clients being disabled when configured traffic or expiry limits are reached;
- client enable/disable and traffic-management API operations;
- a panel REST API and OpenAPI document at `/panel/api/openapi.json`.

Version caveat: these are current upstream docs, not proof that the owner's installed panel build exposes identical fields or behavior. Before integration, inspect the installed version and its own API Docs/OpenAPI schema. Confirm the actual Xray enforcement behavior with a disposable test client and controlled test quota/expiry. Do not infer that client-level traffic accounting is instant or that a configured quota is effective until the test confirms the client is rejected after depletion.

Security architecture:
- The 3X-UI API token is a full-admin credential. It must remain only in the backend secret store; never embed it in the Android app or send it to a client device.
- Backend provisioning must map one Top Private Plug subscription/device policy to a distinct 3X-UI client identity and correct inbound membership.
- Use least privilege if the installed panel supports scoped tokens; otherwise isolate the full-admin token and expose only narrow backend operations.
- The Android client receives only its own connection profile/credential, not panel credentials or other clients' data.
- Credential rotation, suspension, expiry, and quota exhaustion must be tested end-to-end before disabling the current app lease/heartbeat model.

Current status: owner says client-management controls are available, but no 3X-UI version, API schema, test-client result, or endpoint-to-app-profile mapping has been verified. No live client or inbound has been modified.
