# 0.1.8 pilot: failed-connect recovery

Confirmed in 0.1.7 source:

- STOP, onRevoke and onDestroy synchronously enter xrayLock and native stopLoop on Android's main thread. Native startup owns the same lock; native shutdown can wait on I/O. Both paths can freeze all controls.
- Automatic account refresh sets the same busy flag used to disable buttons and reject connect attempts. Two sequential requests can keep actions unavailable for an extended period.
- HTTP 401 from a deleted/invalid account leaves stale local account/profile state visible.
- Tunnel verification exclusively targets the Render admin host; host-specific refusal or availability can reject a tunnel independently of general internet reachability.

Changes:

- Cancel immediately marks Disconnecting and schedules idempotent cleanup on a dedicated thread. New connections wait for native cleanup; main-thread lifecycle callbacks never acquire xrayLock. Close the Android descriptor before waiting on native shutdown and recheck it under the lock to cover concurrent startup.
- Background refresh has its own executor and flag. Foreground actions remain available; outdated refresh results are discarded after token/origin changes.
- Authenticated HTTP 401 clears invalid local access and shows activation instructions. Transient connection errors retain access.
- Probe uses the pinned native core's default HTTPS target, https://www.google.com/generate_204, still through core.Dial. Negative delay is failure; an unexpected native exit retains a failure reason.
- GitHub Actions caches the debug pilot signing key for subsequent builds. Previous APKs signed using different ephemeral keys cannot be updated in place; uninstalling changes Android Keystore identity and requires new access from the admin.

Validation:

- Existing 71 backend tests passed locally before changes.
- Java regression executes the production cleanup methods with blocked startup and shutdown, checking responsive cancellation, one cleanup, descriptor release, and delayed reconnection. Runs with a JDK in CI.
- Full Android build and native VLESS/TLS/HTTP-chain checks run in GitHub Actions.
- No phone is attached. Actual carrier connectivity and the reported upstream EOF remain unverified; do not describe this pilot as a proven working VPN until a phone passes the HTTPS test and loads internet content.
