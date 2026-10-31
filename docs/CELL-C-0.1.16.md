# Cell C support — 0.1.16-pilot

Adds Cell C to the Home and Plans network selectors with an orange accent. Cell C uses the existing assigned Xray/VLESS profile flow, saved-profile bootstrap, account verification and bounded reconnect policy. No credentials or server settings are embedded in the APK.

The admin backend already accepts Cell C VLESS imports and profile assignment. A working Cell C supplier VLESS profile must be imported, enabled and assigned to the account, then saved in the app over Wi-Fi before mobile testing. No Cell C-specific profile was present when checked. Existing Any profiles remain available under the current assignment policy; selecting Cell C alone does not create or validate a carrier route.

Cell C plan requests and support links include the correct network. Prices are requested from the admin because Cell C prices were not supplied. MTN/Telkom plans remain unchanged. Home stays static.

Validation: purchase/support regression harness covers all three networks. Emulator checks require the Cell C selector and preserve static Home assertions. Physical Cell C testing is pending supplier settings.
