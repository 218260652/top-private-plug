# Host Lab 3.0 — standalone Android diagnostics

Host Lab is a native Android application for Android 8.0 or later. It has three screens: Test, Results and Guide. It does not require an account or any cloud service. Results stay on the phone unless the user exports JSON through Android's document picker.

Features: up to 10 hostnames per batch; 1 or 3 measurements; network labels for MTN, Telkom, Cell C, Vodacom and Other; detected active transport and operator name; independent server/SNI/HTTP Host/path/port fields; VLESS TLS endpoint import with credentials discarded; DNS, TCP, certificate-verified TLS, HTTP response and WebSocket upgrade checks; up to one public IPv4 and IPv6 address per host; cancellation; newest-first local history of 100 measurements; safe report export.

VLESS import does not authenticate the VPN. The app does not install a VPN service or route other apps' traffic. It measures endpoint connectivity. Successful HTTPS or WebSocket checks do not prove VPN compatibility or free data. Operator network labels are self-reported; Android transport and operator identification can be ambiguous on dual-SIM phones. Billing always remains unverified.

Build with JDK 17, Android SDK 35 and Gradle 8.9: `gradle --no-daemon assembleDebug lintDebug`. The workflow builds a debug-signed APK for personal testing and verifies its signature and application identity. Keep the same signing key for future updates; a new debug key may require uninstalling the old test build and will remove its local history. No signing credentials are committed. APK compilation does not establish physical-SIM correctness.

The app uses INTERNET and ACCESS_NETWORK_STATE only. It contains no analytics, ads, cloud upload, sign-in, background scanning or phone-identifier collection. Certificate verification cannot be disabled. Export removes UUIDs and query values from request paths; hostnames and remaining path components may still be sensitive. Review reports before sharing.
