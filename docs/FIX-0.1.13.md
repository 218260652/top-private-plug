# 0.1.13: reduce account connection churn and identify upstream failures

The phone report now confirms SAVED_PROFILE_START, ACCOUNT_VIA_TUNNEL, and
TUNNEL_ACCOUNT /v1/challenge HTTP_200. Startup order is working. The next account
request fails, with Xray identifying HTTP CONNECT proxy responses 429 and 503.
These are upstream proxy refusals, not proof of an incorrect phone clock.

The 0.1.12 API forced Connection: close for every request. Remove that header and
leave a fully consumed response eligible for Android connection pooling. Failed
or incomplete responses still disconnect. The explicit loopback Proxy and origin
check are retained: no direct fallback or certificate relaxation is introduced.
This reduces avoidable CONNECT churn but cannot promise upstream availability.

Capture only fixed 429/503 codes from the native callback before diagnostic
truncation. Show actionable proxy messages and a structured UPSTREAM_PROXY code,
with a 30-second app retry pause, rather than a misleading generic TLS message.
No automatic replay of signed authorization POSTs is added.

The saved-profile label now describes cached settings, not a verified network.
Manual Refresh connection settings on Wi-Fi replaces existing cache entries;
automatic refresh still prepares only missing entries. This lets an admin repair
or replace an upstream profile without requiring the user to erase local access.

Validation covers explicit transport selection, eligible successful responses,
disconnection of broken responses, forced profile refresh, proxy code
classification, and temporary-lease cleanup. CI also builds and signs the full
Android pilot and exercises the pinned native chain. A phone test is required to
establish operation on the user's network. Continued proxy 429/503 needs action
by the owner/operator of that upstream proxy or a working assigned profile.
