# Research provenance

The uploaded APKs and supplied screenshots were treated as behavioural/UI references. The new implementation does not reuse their code, resources, signing keys or native engines and does not contact their remote services. No access to their backend, accounts or admin systems was attempted.

`apk-inventory.json` contains independently extracted manifest/package/version/permission/service/native-library metadata and SHA-256 hashes for the two reference files. The first APK includes Go JNI libraries; HA Tunnel includes a SOCKS5/TUN library and TLS-related native libraries. Library presence alone does not prove a complete connection flow.

Earlier conversation reports describe ECDSA device challenges, encrypted profiles, polling and Xray configuration. Those statements were supplied as prior research context. They were not all independently retraced from compiled method bodies in this build turn, and are not claimed as newly verified evidence. No original backend/database source was recovered. The previously located `vpn-foundation` directory only managed entitlements and explicitly did not provision a tunnel; the current package implements a new control plane and gateway.

REA was located in the earlier workspace, but this build used direct manifest inspection and original implementation, not a claimed completed REA decompilation. The build does not require REA to run.

## Primary technical references

- Android VPN service, consent, socket protection, routing and lifecycle: https://developer.android.com/develop/connectivity/vpn
- Android Keystore: https://developer.android.com/privacy-and-security/keystore
- Python TLS API: https://docs.python.org/3/library/ssl.html
- Linux TUN/TAP driver: https://docs.kernel.org/networking/tuntap.html
- aiohttp server reference: https://docs.aiohttp.org/en/stable/web_reference.html
- Caddy releases: https://github.com/caddyserver/caddy/releases
- Eclipse batch Java compiler: https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.user/tasks/task-using_batch_compiler.htm

References guided our own implementation; they do not certify this product. Xray's API was reviewed during design research but Xray is not used in this build.
