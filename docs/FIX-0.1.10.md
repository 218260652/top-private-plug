# 0.1.10 pilot: distinguish account reachability from tunnel failure

Source inspection confirms that `/v1/challenge` and `/v1/connect` must succeed
before Android's TUN and the Xray engine start. The app UID is excluded from the
VPN; authenticated heartbeats also use the underlying network. Thus a working
supplier profile alone does not establish that this app can reach its separate
account service. This is a confirmed architectural difference, not proof of a
carrier fault or a verified comparison with NetMod's internal implementation.

The supplied `uchia.nm` file is encrypted text. Its internal configuration cannot
be compared with the normalized import from that file. No decryption was attempted.

Changes:

- An in-memory, 48-event connection report records fixed startup stages, direct
  API route/status and DNS/TCP/TLS/timeout categories. It accepts no exception
  messages, URLs, server names, profile JSON, tokens or credentials.
- Home, saved-access recovery and Settings expose the report while network work
  is busy. Sharing opens Android's chooser only after the user taps Share.
- The snapshot includes the current transport and Android's validated-internet
  flag. These describe the network when the report is opened, not earlier events
  or the carrier's billing status. Events disappear when the app process ends.
- Heartbeat connect/read timeouts are 5/10 seconds instead of 12/45 seconds,
  giving the 30-second lease watchdog room to fail closed. This is not a total
  request deadline (DNS and repeated reads can take longer). Normal requests keep
  their existing cold-start timeouts.

Authorization, duration, quota, TLS verification and profile contents are unchanged.
No zero-data connectivity is claimed. Do not remove account authorization merely
to make a tunnel start: supplier credentials and subscription limits still matter.

Phone check: keep the existing app installed, update it, turn off other VPNs,
try once on Wi-Fi and once on mobile data, then open Connection report immediately
after each attempt and share the text. A failure at DIRECT_ACCOUNT before
VPN_INTERFACE isolates the account-service dependency; a later failure requires
engine/profile investigation. A connected icon alone is insufficient: verify
browsing and traffic as well.
