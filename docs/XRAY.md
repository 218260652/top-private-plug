# Imported connection pilot — 0.1.4

This is the only connection method offered by the active admin, API and app. There is no manual custom-SNI form. The admin accepts unlocked Trojan-over-TCP/TLS Xray JSON in Connection profiles. It rebuilds an Android TUN configuration, preserves an optional HTTP upstream and literal DNS servers, and strips arbitrary listeners, API, file paths and unsupported global options. NetMod encrypted links are not accepted.

Imported `tcp+local://` DNS addresses are converted to `tcp://` with the same resolver. Local-mode DNS bypasses Xray routing; the converted queries follow the `dns-in` rule through the Trojan outbound. Existing stored profiles are rebuilt when connecting, so they receive this correction without reimporting. This covers DNS handled by the core; resolving the upstream server hostname and the app's direct account API requests still use the underlying network. Physical-device DNS leak tests remain required.

Passwords are stored in the private database, excluded from profile listings and audit, and delivered only after activation and a signed connect challenge. Never commit supplied profiles or passwords. Explicitly choose the unverified-TLS testing option only for profiles that require it; production profiles should verify a valid certificate.

Imported connections use the supplier server, not the Oracle IP. Account checks occur every 5 seconds, with a 30-second watchdog. Expiry, suspension, profile replacement and quota exhaustion stop the unmodified app. Counters measure the Trojan outbound and are APP REPORTED. A modified client or exported/shared upstream password can bypass app controls. This is not independently enforced customer billing on a third-party gateway.

## Build

Use JDK 17, Android SDK platform/build-tools 35 and Go matching the pinned engine go.mod. Check out https://github.com/2dust/AndroidLibXrayLite at 76a6e2172210613fcb4aa32b6de55bcd9452ce43 into `.xray-source`, run `bash tools/build_xray.sh`, then `python tools/build_android.py --sdk "$ANDROID_HOME"`. The build includes ARMv7, ARM64 and x86_64 libraries. CI runs this sequence. The engine is LGPL-3.0, Xray-core is MPL-2.0; license texts are shipped in APK assets. Application and pinned library source accompany the CI build for rebuilding or replacing the library. A debug-signed APK from a fresh runner may require uninstalling a previously signed pilot; uninstalling removes the Android Keystore identity, so the admin must reset that account's device binding while preserving expiry.

## Acceptance on a phone

1. Import a supplier-authorized profile, assign it to a trial account, install the new APK, activate and connect.
2. Connected is shown only after an HTTPS request through the core succeeds. Open websites in another app to verify Android routing and DNS.
3. Verify upload/download changes, disconnect/reconnect, mobile-network switching, and resume after backgrounding.
4. Suspend, expire, exhaust the trial or replace its profile; the unmodified app must disconnect on the next account check. Disconnect API reachability must fail closed within 30 seconds.
5. Verify IPv4/IPv6 and each intended carrier from actual phones. CI does not prove carrier compatibility or third-party server uptime.

Older APKs without Xray support do not receive imported profiles. The active API rejects manual TPP connections, and the new Android app contains only the imported-profile path. Historical database records are preserved. No live carrier test is established by this change.


## Android startup regression

The pinned Xray `infra/conf/tun.go` calls `net.Interfaces()` when the TUN settings have no name. Android denies that interface enumeration. Normalized configs now set `name: tpp0`, and the Android client sets it defensively before starting the core. The Android TUN implementation uses the file descriptor from `VpnService`; the name does not create a second interface. No auto interface selection, system route manipulation or root access is enabled.

CI runs `python tools/verify_android_tun.py --source .xray-source` against the exact pinned dependency. The harness denies socket system calls, verifies that the generated named config parses, and checks that an unnamed control reproduces the interface-permission failure. This is a native configuration regression, not a physical-device routing test.

## Upstream proxy compatibility

Imports may specify the upstream HTTP CONNECT hop in legacy `proxySettings.tag` or current `streamSettings.sockopt.dialerProxy`. The importer resolves the referenced HTTP outbound, preserves the allowed address/port/headers, and emits only `streamSettings.sockopt.dialerProxy`. Conflicting tags are rejected. Re-normalizing a stored profile preserves its upstream; old stored imports are migrated in the connection response without an owner reimport.

The native regression now parses the entire generated Xray configuration, including direct, legacy-proxied, current-proxied and explicitly unverified-TLS variants. It includes negative controls for the removed `proxySettings` field and the unnamed TUN error. This still does not establish live supplier connectivity.

## Explicit legacy test TLS compatibility (0.1.5)

The pinned upstream core removed `allowInsecure:true`. `tools/prepare_xray_compat.py` copies the exact pinned core source into the rebuild tree and applies a small compatibility patch: only an explicit legacy true flag maps to a private test-mode sentinel. The TLS adapter recognizes that sentinel and restores the previous unverified testing behavior. Normal certificate verification remains enabled for ordinary profiles; conflicts with pins/name overrides are rejected. Native policy checks verify both the opt-in and ordinary certificate-name rejection. The patched source and script are included with rebuild sources; this is a modified core, not unmodified upstream behavior.

The importer still requires the owner to select the unverified testing option, and Android still displays its warning. Unverified profiles do not authenticate the supplier. Existing 0.1.4 and older engines cannot run this flag: the API returns an upgrade instruction before issuing a lease. Use the 0.1.5 compatibility APK. Supplier traffic remains unverified until a physical-device test succeeds.


## VLESS supplier replacement

The importer also accepts one VLESS TCP/TLS outbound with one UUID user, encryption `none`, and no flow. It preserves an optional supported TLS fingerprint, translates the legacy HTTP proxy chain to `sockopt.dialerProxy`, and accepts routed DoH at `https://1.1.1.1/dns-query` and `https://dns.google/dns-query`. Inactive WebSocket settings are omitted; this does not switch the server transport. Supplied credentials belong only in the private database.

The outbound retains the historical `trojan` statistics tag so installed 0.1.5 clients continue counting usage for VLESS. This tag is not the protocol: the outbound protocol and credentials are VLESS. Replacing an existing profile preserves account assignments and increments its version, requiring active clients to reconnect. The native parser regression includes VLESS, HTTP chaining, Chrome fingerprint and DoH. Live phone traffic remains a separate acceptance check.

## Startup diagnosis (0.1.6)

Connection progress now distinguishes the account challenge request, device signature, profile authorization, Android VPN creation, native Xray startup, and tunneled HTTPS check. Failures retain their stage. The watchdog starts before the account requests (75-second overall startup budget), then uses the existing 30-second lease limit after authorization. It publishes timeout state before native cleanup. This helps identify the failure on a real phone; it does not establish a successful tunnel. The supplier VLESS configuration and DNS settings are unchanged.

The supplied NetMod 4.3.0 log reports Xray 26.1.23, SOCKS port 10808, outbound DNS 209.212.96.1/209.212.97.1 and custom DNS 1.1.1.1/1.0.0.1. Our pinned library uses a later core revision with native TUN support, and the account API is reached before engine startup. Matching protocol JSON does not establish identical network behaviour. Do not change the upstream or DNS solely from the successful startup log: it has no failed request or handshake trace.
