# Verification status — 27 October 2026

## Completed locally

**42 automated tests passed** using aiohttp 3.14.5 and cryptography 50.0.2.

- Account-control tests: atomic first activation; 7/15/30-day periods; custom trial hours; changing an active trial duration; replay, invalid proof and foreign-device rejection; concurrent activation; durable quota arithmetic; concurrent charges; one session per account; ticket reuse rejection; expiry; suspension/deletion; profile updates; rebind preserving expiry; renewal; password sessions; TOTP vector; absence of raw codes/tokens in account storage.
- HTTP API tests: admin authentication, origin/CSRF checks, cookie attributes/logout, full admin-to-client activation flow, login rate limits, static UI assets/security headers, client/admin separation, oversized requests.
- Gateway integration tests: real local TLS sockets and test certificates; authenticated handshake; framed packets roundtrip through a **simulated packet device**; both-direction accounting; quota cutoff; idle suspension/expiry cutoff; private/spoofed packet rejection; invalid tickets; untrusted certificate rejection; malformed packet and IPv6 rejection.
- Android sources compiled; DEX generated; APK aligned; APK v2/v3 signatures verified. Parsed APK package: `za.co.topprivateplug`; version: `0.1.1-pilot`; minimum Android API 26; target API 35. Debug signed and debuggable.
- JavaScript syntax and Python compile checks. Caddy configuration parsed with the Caddy binary; Compose YAML parsed. No Docker daemon was available to execute the stack.
- Runtime package versions checked against PyPI's version-specific vulnerability metadata. See `dependency-check.json`; this is not a full supply-chain/security audit and cannot discover unreported vulnerabilities.

## Not verified / not completed

- Actual Android installation, screenshots from a running APK, runtime compatibility and permission lifecycle on a physical phone.
- Actual Linux TUN routing, forwarding, NAT, public internet access, DNS leak behaviour, public-IP change and a live domain/certificate.
- Real deployment of Docker containers, first certificate issuance, persistent volume backup/restore and reboot recovery.
- Commercial capacity, TCP-over-TCP performance, packet-loss recovery, roaming/reconnect and battery consumption.
- Carrier-specific connectivity on MTN, Telkom or Cell C. No carrier billing bypass or free internet is included.
- Browser visual and interaction review of the admin dashboard. Static resources and API routes are tested, but the attempted browser runtime installation did not complete in this environment.
- Independent security audit, store-ready release signing and publication.

## Risk assessment

| Priority | Finding / limitation | Action |
| --- | --- | --- |
| Release blocker | No live gateway or phone-to-internet acceptance test | Provision VPS/domain, then complete deploy/README.md checks |
| Release blocker | New custom TLS packet protocol has no independent review | Audit transport, state transitions and packet handling before commercial release |
| High | Strict per-packet SQLite commits and TCP-over-TCP may limit throughput | Benchmark the intended customer load; migrate transport/accounting only with enforcement tests |
| High | Pilot APK is debug signed and debuggable | Use owner-controlled release signing and a release build for distribution |
| Medium | No kill switch or always-on mode; normal network resumes after disconnect | Keep UI disclosure; implement and test stricter mode if required |
| Medium | IPv4 only; IPv6 intentionally blocked during connection | Verify block on a real dual-stack phone; implement IPv6 only with matching gateway support |
| Medium | One-node database; disk loss loses account records without backup | Encrypted off-host backups and restore drills |
| Medium | Public TLS/API endpoints need operational abuse controls | Restrict admin access where possible, enable MFA, set provider firewall/rate controls and monitor resource usage |

No production readiness claim is made. Do not sell access based solely on an APK installing or a Connected status.

## WhatsApp update: 0.1.1 pilot

Added customer-initiated purchase/top-up requests to +27 70 384 1868, plan selection, and a non-secret account reference. Admin account search accepts that reference. Access codes, login tokens and device secrets are excluded from messages. A WhatsApp launch never changes entitlement or marks payment as received. The updated APK compiled and its v2/v3 signatures verify; it uses the same signing certificate as 0.1.0 and a higher version code. JavaScript syntax was checked. The existing 42 backend tests cover the unchanged entitlement engine; no WhatsApp message was sent or on-device WhatsApp handoff tested.
