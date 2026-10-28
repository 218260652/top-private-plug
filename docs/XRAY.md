# Trojan import pilot

The admin accepts unlocked Trojan-over-TCP/TLS Xray JSON in Connection profiles. It rebuilds an Android TUN configuration, preserves an optional HTTP upstream and literal DNS servers, and strips arbitrary listeners, API, file paths and unsupported global options. NetMod encrypted links are not accepted.

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

Older APKs do not advertise Xray support and are not shown imported profiles. TPP behavior stays available. No live Oracle gateway or live carrier test has been established by this change.

