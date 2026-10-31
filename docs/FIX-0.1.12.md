# 0.1.12: provision the saved connection before mobile testing

The phone report showed DIRECT_ACCOUNT /v1/challenge with no SAVED_PROFILE_START.
The 0.1.11 implementation cached profile metadata at account refresh, but cached
native configuration only after a successful Connect. A user who refreshed or
activated on Wi-Fi and then switched networks could therefore still have no
bootstrap configuration for the chosen carrier.

0.1.12 prepares every missing assigned Xray configuration during online account
refresh and activation. It uses the existing signed connect API for compatibility,
encrypts the configuration in the account-scoped Vault, and releases each
short-lived lease immediately, including when saving fails. It opens no VPN or
native engine during preparation. Cached profiles still require fresh account
approval through the restricted VLESS/Trojan control proxy before traffic.

The UI shows readiness for the chosen carrier and offers Save connection settings
on Wi-Fi. Automatic direct refresh is skipped without validated internet;
connection attempts without either a saved profile or validated internet explain
exactly what is missing before making a direct challenge request. The service
also enforces this guard. If several carrier profiles exist, an offline attempt
selects one with a saved configuration. Reports include carrier cache readiness.
Account operations cannot overlap profile preparation. HTTPS requests disable
socket reuse to keep direct and loopback-proxy phases separate.

Test by updating in place, opening on Wi-Fi, waiting for Ready for mobile
connection for Telkom, then switching Wi-Fi off and pressing Connect. The report
must show SAVED_PROFILE_START and TUNNEL_ACCOUNT. Carrier reachability is a phone
test and is not established by build or native fixture tests.
