# TPP/1 transport and API contract

## Activation and entitlement

1. App creates a non-exportable P-256 key in Android Keystore.
2. `POST /v1/challenge` with `public_key` (Base64 DER SubjectPublicKeyInfo) and `purpose` (`activate` or `connect`) returns a 60-second nonce message and ID.
3. App signs the exact UTF-8 message with SHA256withECDSA. Signature is Base64 DER ECDSA.
4. `POST /v1/activate` with `code`, `public_key`, `challenge_id`, `signature` redeems the code atomically and returns a token and account. Repeated redemption with the same device key preserves activation and expiry. Other devices are rejected. The server stores only token/code hashes.
5. Client bearer tokens protect `/v1/status`, `/v1/profiles`, `/v1/usage?hours=1|6|24`, `/v1/connect` and `/v1/disconnect`.
6. `/v1/connect` additionally requires a signed `connect` challenge and an assigned `profile_id`. It returns a single-use ticket valid for 30 seconds and the latest profile.
7. The gateway authenticates that ticket, SNI and TLS version. One active tunnel is permitted per account. Expired, suspended, deleted and exhausted accounts cannot open tunnels.

Byte quantities use decimal MB and GB (1 GB = 1,000,000,000 bytes), count both directions at IP-packet level, and exclude TLS framing and mobile-provider overhead. A packet is charged durably before forwarding. The gateway refuses any packet that would exceed the quota. Transport failure after charging may conservatively count undelivered data; quotas do not reset on reconnect or restart. A change to the phone clock does not affect backend entitlement. Secure server time / NTP remains an operational requirement.

## TLS connection and frames

TLS 1.2 minimum, TLS 1.3 selectable; no SSLv2/3, TLS 1.0/1.1 or verification bypass. Android validates the trust chain and the configured SNI hostname against the certificate. The raw socket is bound and protected with Android's `VpnService.protect` before connecting. No trust-all managers, copied private keys, HTTP injection or carrier billing bypass is present.

Every frame is a 4-byte unsigned network-order length followed by that many bytes. Handshake frames are JSON objects, maximum 8192 bytes.

Client first frame:

```json
{"protocol":"TPP/1","ticket":"ONE_USE_TICKET"}
```

Server accepts with:

```json
{"ok":true,"address":"10.77.0.6","prefix":30,"dns":"1.1.1.1","mtu":1400,"protocol":"TPP/1"}
```

Or rejects with `{"ok":false,"error":"..."}`. Address shown is an example; the server assigns an account a stable `/30` slot from `10.77.0.0/16`. Slots are never reused across accounts, including deleted accounts, to avoid stale NAT state crossing customer boundaries. The pilot supports at most 15,999 distinct account address allocations before an operator-managed pool migration.

After acceptance the first byte identifies frame type:

| Type | Payload | Direction |
| --- | --- | --- |
| 1 | IPv4 packet, 20–1400 bytes | Both |
| 2 | 8-byte monotonic timestamp | Client heartbeat |
| 3 | Same 8-byte timestamp | Server heartbeat response |
| 4 | UTF-8 error, then close | Server |

The gateway validates packet length, IP version, assigned source address and public destination. Private, metadata, multicast and spoofed destinations/sources are dropped. The deployment firewall independently isolates the host and private networks. IPv6 is captured and dropped by the Android pilot; it is not sent directly outside the tunnel.

Heartbeat every 10 seconds; read timeout 45 seconds server-side and 35 seconds Android-side. Expiry and revocation are checked per packet and every second while idle. These are code intervals, not production latency guarantees. Profile version changes require reconnection. Android shows Connected only after TLS authentication and local VPN interface setup, but public-IP and browsing tests are still needed to prove upstream routing.

## Admin API

Same-origin dashboard under `/admin/`. Secure HttpOnly SameSite=Strict cookies, eight-hour sessions. Every modifying request requires matching `Origin` and `X-TPP-Request: 1`; no permissive CORS.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /admin/api/login | Username, password, optional `otp` |
| POST | /admin/api/logout | Invalidate session |
| GET | /admin/api/state | Accounts, profiles, recent audit events |
| POST | /admin/api/accounts | Label, kind, `duration_seconds`, `quota_bytes`, `profile_ids` |
| PATCH | /admin/api/accounts/{id} | Label, suspended, quota_bytes, duration_seconds, extend_seconds, reset_device |
| DELETE | /admin/api/accounts/{id} | Revoke tokens/tickets/sessions; tombstone account |
| POST | /admin/api/profiles | Create profile |
| PUT | /admin/api/profiles/{id} | Edit profile; increment version |

Changing `duration_seconds` sets total lifetime from original activation. `extend_seconds` adds time from current expiry, or from now if already expired. Resetting the device key never resets activation or expiry. Admin profiles hold public host/port/SNI information, not a source of mobile data or automatic infrastructure provisioning.
