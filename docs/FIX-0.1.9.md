# 0.1.9 pilot: saved activation after account-service failure

Phone evidence: account challenge and account refresh both fail to open a TCP connection to the Render HTTPS origin, before native tunnel creation. After reopening, the token still exists (the home screen is visible), but account/profile objects are empty because they are process memory. The old toggle incorrectly treats a missing account object as requiring activation and the home screen falsely claims no profile is assigned.

The service health endpoint responded with status ok during investigation, using the imported-profile method. This establishes reachability from the diagnostic browser, not the user's MTN connection. The cause of the phone-side network failure remains unverified.

Changes: use a distinct CHECK_REQUIRED state when an activation token exists but account information is missing; show saved-access recovery and retry/status buttons; suppress false missing-profile claims until account details load; retain server authorization before starting any tunnel. Transport failures provide recovery guidance and preserve the token. Only authenticated rejection of the current token clears it.

No persistent profile cache, offline authorization, certificate-validation bypass, account replacement, or duration/quota changes are introduced. Existing 0.1.8 installs should update in place using the cached pilot signing key.

Validation: Java account-gate regression covers process restart, unavailable refresh, missing token, valid account, expired/suspended/deleted/exhausted account, and prevention of offline authorization. Existing shutdown and backend checks run too. Actual MTN reachability and successful phone tunneling still require device verification.
