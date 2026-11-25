# Salvation Mahumane VPN interface build

The Android interface follows the two owner-supplied screenshots: gold activation screen with a globe, and navy home screen with gold ribbons, account details, traffic counters, and an MTN/Telkom banner. Content adapts to device size. Screenshot account names, expiry dates, counters and connection state are replaced by live values. Error text appears after a failed request. The activation draft survives in-session rerenders.

- Installable package: `za.co.salvationmahumane.vpn` (alongside Top Private Plug).
- Existing Java namespace and native VPN engine retained.
- Existing dashboard endpoint retained: `https://top-private-plug-admin.onrender.com`.
- Paid one-device and shared 50-device trial rules are enforced by the existing backend.
- Home menu retains access to usage, plans, account, settings, updates and network selection including Cell C.
- The screenshot WhatsApp group button has no destination until the owner supplies the invite. Configure `whatsapp_group_url` in `res/values/branding.xml`.
- Original-brand update checks are disabled for the new package until its own update service is configured.
- This build is debug-signed for review. A phone/carrier connection check remains necessary. No backend or live dashboard changes are deployed by this branch.

Build with `python tools/build_android.py --sdk ANDROID_SDK_PATH` after building the pinned Xray AAR as documented in XRAY.md. Version 0.2.14 is the starting engine version.
