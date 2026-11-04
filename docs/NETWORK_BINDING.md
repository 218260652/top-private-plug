# Network-bound activation and first-screen cleanup

Candidate 0.1.21-pilot (version code 22), upgrade baseline 0.1.20-pilot.
Remove the first-screen settings gear, purchase row, payment/renewal explanation
and bottom navigation. Keep code entry, trial entry and three network choices.

Admin code issuance requires exactly one account carrier: MTN, Cell C or Telkom.
Assigned profiles must match it or be labelled Any. Editing a binding validates
its profile assignment. An Any supplier profile is transport reuse, not an
all-network access code. A profile relabel cannot expand an existing grant.

Public activation compares the selected carrier against the account's carrier
inside the redemption transaction, before device registration, token rotation,
or activation/expiry changes. Missing/wrong selection returns a fixed safe 422.
New bearer tokens are recorded with their network. Authenticated requests must
send X-TPP-Network matching both token and account. The app also validates the
returned account carrier before writing its encrypted network slot. New app
activations and connects require network_binding_version 1 from /health, so an
older backend cannot silently accept the new client without enforcement.

The schema migration adds accounts.carrier and token_networks. It does not
change quotas, usage, expiry, activation times, device keys or existing tokens.
Unique specific legacy assignments are inferred. Any-only/mixed legacy accounts
stay unassigned until an admin chooses their carrier and compatible profiles.
Older installed clients retain existing legacy-token access; new activations
must use the updated client. This is an intentional compatibility boundary,
not enforcement of the physical SIM: a self-reported selection cannot prove
carrier attachment, especially on Wi-Fi.

Backend-only deployment is prepared separately from the unmerged Android/UI
branch to avoid releasing unrelated changes. Production deployment and public
APK publication remain subject to the owner's release approval. Do not claim
this policy is live before /health reports network_binding_version 1.
