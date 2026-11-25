# Salvation Mahumane VPN interface build

The Android interface follows the two owner-supplied screenshots: gold activation screen with a globe, and navy home screen with gold ribbons, account details, traffic counters, and an MTN/Telkom banner. Content adapts to device size. Screenshot account names, expiry dates, counters and connection state are replaced by live values. Error text appears after a failed request. The activation draft survives in-session rerenders.

- Installable package: `za.co.salvationmahumane.vpn` (alongside Top Private Plug).
- Existing Java namespace and native VPN engine retained.
- Existing dashboard endpoint retained: `https://top-private-plug-admin.onrender.com`.
- Paid one-device and shared 50-device trial rules are enforced by the existing backend.
- Home menu retains access to usage, plans, account, settings, updates and network selection including Cell C.
- Until a group invite is supplied, the home screen opens WhatsApp support. Configure `whatsapp_group_url` in `res/values/branding.xml` to use the group instead.
- Architecture-specific update feeds use the Salvation download site, with HTTPS host, SHA-256, package/version and signing-certificate verification.
- Version 1.0.0 uses a dedicated owner release signing key. Public source and download archives contain no signing secrets. A phone/carrier connection check remains necessary.

Build with `python tools/build_android.py --sdk ANDROID_SDK_PATH` after building the pinned Xray AAR as documented in XRAY.md. Version 0.2.14 is the starting engine version; Salvation app version is 1.0.0 (versionCode 100).

## Matching admin dashboard

The dashboard sign-in, setup, overview, account lists, profile import, activity and edit dialogs use the Salvation name, gold shield, dark navy/black cards, gold borders and buttons, and ribbon background. Responsive layouts support phones and desktops. Dashboard authentication, existing endpoint paths, VLESS import, code creation, paid/trial device rules and account actions retain their original behavior. No existing hosting, database, service or environment-variable identifiers were renamed.

## Release delivery

Public download page: https://salvation-mahumane-vpn.ramashiaandrew3.chatgpt.site/ . Downloads include arm64-v8a and armeabi-v7a builds, checksum files and architecture-specific update manifests. The Samsung A05s uses the 64-bit build.

Build a release with `tools/build_android.py --abi arm64-v8a --keystore /private/path/salvation-release.p12 --storepass-env SALVATION_SIGNING_PASSWORD` (plus SDK/ECJ options as needed). The keystore and password backup is private to the owner and must never enter the repository or public download site.

The earlier debug-signed Salvation pilot must be uninstalled before installing the release-signed app. A consumed paid-device binding may need an admin reset, preserving expiry and usage. Top Private Plug has a different package and can remain installed. Existing accounts and imports use the existing Render/Neon backend. Physical MTN/Telkom/Cell C connection and expiry/quota checks remain part of device acceptance; a successful web deployment is not a proof of supplier routing.

## Deployment status — 25 November 2026

The public download Site deployed successfully. Both published phone APK downloads match their SHA-256 feed values. The Render deployment of commit f61d283263a0dabcdf2f690696c0688da0fac129 failed its pre-start PostgreSQL check: Neon returned "Your account or project has exceeded the quota. Upgrade your plan to increase limits." No database records or hosting billing settings were changed. The full service must not be called customer-ready until database access is restored, Render is successfully redeployed, and phone connectivity has been verified.
