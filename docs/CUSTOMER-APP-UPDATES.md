# Customer app updates

Customers on Build 53 and later can open **App updates** in the account menu.
They sign in, check for a newer build, and tap **Update** to download and open
Android's installer. The first install may require permission to install from
Top Private Plug. The downloaded APK must match the installed package and
signing certificate and must have the version and SHA-256 in the release manifest.

## Publish a release

Deploy the customer backend with the app update routes. Set
`TPP_CUSTOMER_UPDATE_DIR` to a private, persistent directory readable by the
customer service. Use the verified, decrypted, signed staging APK. Do not place
it in a public download directory because it contains the bundled test profile.

1. Calculate its SHA-256 and byte size. Copy the APK to
   `<TPP_CUSTOMER_UPDATE_DIR>/<sha256>.apk`.
2. Write `latest.json` in the same directory with `version_code` (integer),
   `version_name` (string), `sha256` (lowercase hex), and `size` (bytes).
   Rename the complete manifest into place after the APK is present.
3. Use a signed-in test account with Build 53 or later to check and install.
   Confirm that unauthenticated requests cannot retrieve the APK.

Without a configured directory, the feed advertises no release. Do not use
Build 53 as the update target for another Build 53 installation. Existing
installations prior to Build 53 need one manual upgrade to enable this menu.
