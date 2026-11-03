# Simple interface and saved network activations

Candidate 0.1.20-pilot, code 21. No production publication or backend schema changes.

The activated home is a single scrollable screen based on the supplied template:
brand, South Africa, MTN / Cell C / Telkom, session upload/download/latency,
selected account quota/used/remaining/expiry, refresh, Connect/Disconnect,
Add / renew activation, About & licenses (with diagnostic report and update check).
There is no activated payment, plan purchase or bottom navigation interface.
The first activation page retains its original content and adds network selection.

Each network owns encrypted token/account/catalog/bootstrap/history values.
Existing encrypted access migrates atomically into the single matching network
when the catalog has one specific carrier, otherwise MTN. No device key or
Keystore alias changes. Switching requires Disconnected and no pending request.
Each code retains its original server account limits and expiry. Saving the same
account in another network slot does not grant it extra profiles or data.
Reactivation rotates that account's token in all saved slots for that account,
re-scoping cached data without touching unrelated accounts. Logout clears only
the selected slot; changing service origin clears all slots.

Activation success is distinct from fetching/saving bootstrap profiles. Temporary
profile fetch/lease conflicts show an inline retry notice, not a false activation
failure. The previous HTTP status preservation fix is included. A generic 409 no
longer asserts that disconnecting is the universal solution.

Automated emulator coverage exercises encrypted legacy migration, three separate
accounts, per-slot bootstrap isolation, token rotation when reusing an account,
logout isolation, stale overview labeling, active-tunnel switching rejection,
50 overlapping refresh taps and single-screen snapshots. A sentinel checks that
APK installation preserves preferences. The package and signing identity remain
unchanged; versionCode is higher than 0.1.18 and 0.1.19.

Actual carrier connectivity, zero-bundle behaviour, supplier availability and
long-running stability still require the user's phone. No claim of fixing the
underlying server/network failure is made without a connection report.
