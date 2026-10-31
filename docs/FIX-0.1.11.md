# 0.1.11 pilot: saved VLESS first, account authorization through it

Requested order: start the supplied connection, verify the account over that path,
then enable normal traffic. The prior phone evidence failed at the direct account
challenge on the zero-data SIM, while Wi-Fi reached Connected.

The first authorized connect saves only the normalized config and profile metadata
in AES-GCM storage backed by Android Keystore. The catalog is stored separately
with the same protection. Both are scoped to a digest of service origin + access
token, and cleared on token/service changes and Forget. Session leases are excluded.
An update from 0.1.10 needs one Wi-Fi/ordinary-data connection to populate this cache.

When a saved profile exists, the native core starts with descriptor 0 (documented
by the pinned controller as no TUN). It has a single loopback HTTP inbound. Rules
permit that inbound to the exact account HTTPS host and port via VLESS/Trojan,
then block every other target. There is no Android VPN interface or general-traffic
inbound until a fresh signed challenge and `/v1/connect` approval succeed through
this proxy. Android HTTPS certificate checks for the account server remain enabled,
redirects are disabled, and the account endpoint is never rewritten to localhost.

After approval, stop the restricted core, start the current authorized config with
the Android TUN and the same restricted control proxy, then check tunnel traffic.
Account refreshes and heartbeats use the explicit loopback HTTP proxy despite the
app UID bypassing the TUN. Account expiry, suspension, quota and leases continue
to be checked online; failure disconnects. No backend change or new endpoint is
required. A stale cached supplier profile can fail before it reaches account
verification; Wi-Fi is needed to refresh it in that case.

Validation includes Java policy generation for exact hosts/ports, final deny and
loopback binding; production Api proxy selection without direct fallback during
an origin change; existing cancellation/recovery/privacy and backend tests; native
VLESS/TLS/HTTP proxy fixtures with account-only bootstrap positive/negative controls;
and Android compilation/signature checks. These do not establish zero-data carrier
routing on a physical phone. The existing explicit unverified-supplier-TLS test
option is preserved; this change does not disable any additional TLS checks.
