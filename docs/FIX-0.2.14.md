# 0.2.14 — VLESS/Xray carrier connectivity and reconnect fixes

Version 0.2.14 keeps the existing logo, colours, activation/login screen and dashboard.
It changes only the connection path.

## Reported failures addressed

**MTN/Telkom: "Connected" but pages never load.**
Android was given an IPv6 address and `::/0` route, so AAAA answers sent traffic into
the tunnel. Supplier VLESS/Trojan servers carry IPv4 only, so those connections hung
until the app timed out. The IPv6 route is still installed (so nothing leaks to the
carrier), but the client now blocks IPv6 destinations ahead of the profile's catch-all
rule. Apps fail fast and fall back to IPv4.

**DNS.**
The tunnel advertised one resolver. It now advertises `1.1.1.1` and `8.8.8.8`; queries
still follow the profile's `port 53 → dns-out` rule, and the backend continues to
convert `tcp+local://` resolvers to TCP so DNS survives UDP blocking.

**Reconnect loop.**
A `409 Device already connected` answer was classified as terminal, so a lost response
on a mobile network ended the connection for good. It is now a recoverable lease
conflict: it is retried after the 35-second lease cooldown. The client also releases its
server lease before native cleanup, while the tunnel can still carry the request, and
the reconnect path no longer hits an overlapping-session conflict.

**Network changes.**
Switching Wi-Fi ↔ mobile data had no event handler, so the app stayed "Connected" on a
dead tunnel until the 30-second lease watchdog fired. A default-network callback now
triggers an immediate reconnect, ignoring the handover Android performs while the
interface is being created.

**Mobile data could not save a profile.**
`NET_CAPABILITY_VALIDATED` is often absent on MTN/Telkom APNs. The refresh/connect gates
now require a usable `NET_CAPABILITY_INTERNET` connection instead. Requests still fail
closed, and the connection report still shows the validated flag.

**Account control routing.**
Account-control rules now use the tunnel outbound tag discovered in the profile instead
of assuming a protocol name, so a VLESS or Trojan profile cannot break account access.

## Version

`versionCode 19`, `versionName 0.2.14`, APK `Top-private-Plug-0.2.14-pilot.apk`.
