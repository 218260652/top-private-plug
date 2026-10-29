# Top private Plug — 0.1.10 pilot

Android VPN client and hosted account admin using imported VLESS or Trojan over TCP/TLS Xray JSON. Manual server/custom-SNI profile creation and the TPP connection path have been removed from the active admin/API and Android app.

## Connection reports in 0.1.10

Home, saved-access recovery and Settings include a Connection report button. Retry a failing connection, then open the report before closing the app. It records fixed startup stages, account HTTP statuses and DNS/TCP/TLS/timeout categories without credentials or profile contents. Tap Share to open Android's chooser. See [docs/FIX-0.1.10.md](docs/FIX-0.1.10.md) for scope and phone checks.

Account authorization is required before the tunnel starts. Account heartbeats also use the underlying network because the app UID bypasses the TUN. A supplier profile that works in another client does not establish reachability to this separate account service. This pilot does not claim zero-data support. Heartbeat timeouts now fit inside the 30-second lease under ordinary network conditions; the watchdog remains the final limit.

## Connect

1. Sign in at https://top-private-plug-admin.onrender.com/admin/.
2. Open Connection profiles, paste the unlocked connection JSON supplied for use with NetMod, and enable the import. Encrypted NetMod links and standalone passwords are not supported.
3. Create an access code with the desired duration, quota and imported profile. Existing imported profiles and customer records are preserved.
4. Install the current pilot APK, activate the assigned code and approve Android's VPN permission. Time starts on first activation; repeat activation does not restart expiry.
5. Connect, then verify browsing in another app and the public IP. Confirm expiry, suspension, quota exhaustion and network transitions on a physical phone.

The imported JSON supplies the server, TLS hostname and optional HTTP upstream. Those settings are required by the underlying protocol, but there is no separate manual SNI form. This is compatible with the supported unlocked Trojan configuration format, not a clone of NetMod's application or encrypted format. MTN/Telkom/Cell C are labels; the profile and underlying connection determine actual compatibility.

## What changed in 0.1.4 / 0.1.5

- Migrate legacy upstream proxy settings to the current Xray dialerProxy field. The 0.1.5 native compatibility build supports only explicitly opted-in legacy unverified TLS; ordinary profiles continue verifying certificates. See [docs/XRAY.md](docs/XRAY.md) for the modified core and its checks.
- Give Xray's Android TUN inbound an explicit name. This avoids the desktop interface-discovery call that produced `netlinkrib: permission denied` on Android. Android supplies the VPN file descriptor; no root permission is requested.
- Rebuild previously stored imports on connect, applying the TUN-name and routed-DNS fixes without reimporting.
- Use imported profiles only in the app/admin/API. Historical manual profiles remain in storage but cannot be created, assigned or connected through the active API.
- Show connection state promptly, allow cancellation while account refresh is busy, replace the unsupported power glyph with readable connect/cancel/stop text, and report the actual account-refresh error.

## Accounts and limits

Admin controls paid/trial durations, data quotas, renewals, suspension, deletion and device rebind. Codes are shown once and stored as hashes; activation uses an Android Keystore device identity. Purchases/top-ups open a WhatsApp request to +27 70 384 1868; the owner verifies payment and updates access.

Imported-profile byte counters are APP REPORTED. An unmodified app checks account status and stops after a failed check or watchdog timeout. A modified app or shared upstream password can bypass those controls; this service does not independently enforce billing at a third-party supplier server. Unverified-TLS imports require an explicit test option and do not authenticate the supplier server. No production certification, mobile-data subsidy or carrier bypass is claimed.

## Build and verification

See [docs/XRAY.md](docs/XRAY.md) for the pinned native engine, licenses and rebuild instructions. GitHub Actions runs Python tests, dashboard syntax checks, a native-parser regression under denied socket access, and the Android build. An explicit-name success and unnamed failure under the same restriction check the reported startup regression; they do not prove live supplier routing.

```bash
python -m pip install -r requirements.lock
python -m unittest discover -s tests -v
```

The pilot is debug-signed. CI builds generate temporary signing keys and may require uninstalling an earlier pilot. Uninstalling removes its device identity; the admin must reset that account's device binding without resetting expiry. Owner-controlled release signing remains necessary for dependable commercial upgrades.

The admin/API is hosted on Render with Neon PostgreSQL. See [docs/HOSTING.md](docs/HOSTING.md) for credential setup. The old dedicated TPP gateway modules, scripts and their tests remain historical source; they are not an alternative connection method in this release. An Oracle VPS is not required for the imported-profile connection path.

## Privacy and runtime limits

The service stores activation time, device public key, access state and byte totals. Supplier passwords stay in the private database and are delivered only after authentication and device proof. Core DNS queries follow the tunnel; upstream hostname resolution and direct account API calls use the underlying network. No always-on mode or kill switch is included. A disconnect restores the normal network. Physical-device routing, DNS/IPv6, roaming, battery and supplier uptime must be tested before customer use.
