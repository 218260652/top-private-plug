# 0.1.19 stability development review

This development patch does not publish an APK, change hosting, alter account limits or enable remote telemetry.

## Implemented

- The connection report includes bounded, credential-safe events and the last classified failure. Only fixed stages, approved API path names, numeric HTTP statuses and error categories enter the report; raw exception text, tokens, addresses and configuration bodies do not.
- Transient recovery has no lifetime five-attempt cutoff. Backoff remains bounded at 60 seconds; explicit authorization rejection, certificate failure, manual stop and changed account credentials remain terminal.
- A successful heartbeat after 60 stable connected seconds resets the backoff. Retry waiting pauses when no physical internet-capable network exists, including unvalidated mobile networks; a validated-data flag is not required for the saved-profile path.
- Physical network availability/loss is recorded. A returned network expedites pending retry only when no old authorized lease remains and no upstream/rate-limit cooldown applies. A healthy tunnel is not torn down merely because another network appears.
- The first reconnect can run after two seconds if the server confirmed the old session was released. If cleanup cannot confirm release, the existing 35-second cooldown prevents overlapping legacy 30-second leases. HTTP 429 and upstream cooldowns are still respected.
- API database work runs on worker threads behind a four-slot gate, preserving full synchronous Store transactions on one worker. Request cancellation keeps the slot until its transaction finishes. The email outbox uses thread-safe wakeups and offloads its own database operations too.
- A regression test holds an account lookup blocked while checking that health requests remain responsive. Existing API authorization, quota and profile-email tests still run.

## Changes requiring a coordinated protocol revision

The existing app and server still use five-second heartbeats with 30-second account leases. Merely increasing the client timer would still yield a server 403 once the old lease expired. Merely treating every 403 as temporary would bypass real suspension, expiry or quota enforcement.

A five-minute offline window needs explicit server authorization, a monotonic client deadline bounded by account expiry, local upload-plus-download accounting against the last confirmed remaining allowance, and reconciliation before replacing an old lease. Shared trials need separate treatment: giving 50 devices each the entire cached remaining balance can multiply offline consumption. A local cached expiry alone cannot establish that an account is still unrevoked.

Fast reconnection after an unconfirmed release also needs a same-device, freshly authenticated lease replacement protocol and tests covering concurrent reconnects and usage reconciliation. The patch only accelerates confirmed releases.

## Not enabled by this patch

Always-on, boot restoration and sticky process restart need coordinated lifecycle and encrypted selected-profile restoration tests. A flag change or boot receiver alone does not safely restore account authorization. Battery optimization behavior must be tested on the Samsung A05s with the screen off.

No Sentry or Crashlytics integration is added: local safe diagnostics first avoids collecting supplier credentials or adding a new account dependency. Real crash/process-loss evidence is still outstanding.

No keep-alive monitor or hosting migration is created. Active successful heartbeats should already prevent normal Render idle sleep. Render cold starts remain relevant at first connection or after a real outage, but are not established as the current cause. Fly.io is usage-billed rather than an always-free host. The backend already uses Neon and existing account/device primary-key indexes; duplicating them or caching authorization without revocation handling is not a blanket fix.

## Validation boundaries

Local tests cannot establish carrier throughput, Samsung process survival, handover behavior or the cause of the reported phone disconnect. CI must run Java recovery/diagnostic tests, Android compilation, signing comparison against 0.1.18, emulator update compatibility and the existing UI checks. Before release, reproduce the problem on the actual phone and compare the safe failure report with screen-on/screen-off, Wi-Fi/mobile and normal-download behavior.

No VPS speed test or bandwidth guarantee is claimed. A new iperf server or inbound port would require identifying and authorizing the actual supplier/VPS in use. The code has no configured Mbps shaper, but upstream capacity and carrier/supplier throttling remain unmeasured.
