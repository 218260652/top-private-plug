package za.co.topprivateplug;

import org.json.JSONObject;
import java.util.UUID;

final class CustomerApi {
    private static final String PREFIX = "/v2/customer/";
    private static final Object SESSIONS = new Object();
    private final Vault vault;
    private final Api api;

    CustomerApi(Vault vault) {
        if (!vault.staging) throw new IllegalArgumentException("Staging app required");
        this.vault = vault;
        api = new Api(vault);
    }

    private JSONObject proof(String purpose) throws Exception {
        String key = DeviceKey.publicKey();
        JSONObject challenge = api.request(PREFIX + "challenge",
            new JSONObject().put("public_key", key).put("purpose", "customer-" + purpose), false);
        return new JSONObject().put("public_key", key).put("challenge_id", challenge.getString("id"))
            .put("signature", DeviceKey.sign(challenge.getString("message")));
    }

    JSONObject login(String username, String password, boolean persist) throws Exception {
        synchronized (SESSIONS) {
            JSONObject result = api.request(PREFIX + "login",
                proof("login").put("username", username).put("password", password), false);
            save(result, UUID.randomUUID().toString(), persist);
            return result.getJSONObject("account");
        }
    }

    private void save(JSONObject result, String marker, boolean persist) throws Exception {
        vault.customerSession(new JSONObject().put("access", result.getString("access_token"))
            .put("refresh", result.getString("refresh_token")).put("marker", marker).put("persist", persist));
    }

    JSONObject call(String operation, JSONObject data) throws Exception {
        JSONObject session = vault.customerSession();
        try {
            return api.request(PREFIX + operation, data, session.getString("access"));
        } catch (Api.HttpError error) {
            if (error.status != 401) throw error;
        }
        synchronized (SESSIONS) {
            JSONObject current = vault.customerSession();
            if (!session.getString("marker").equals(current.optString("marker"))) throw new Exception("Sign in again.");
            if (session.getString("access").equals(current.getString("access"))) {
                try {
                    JSONObject result = api.request(PREFIX + "refresh",
                        proof("refresh").put("refresh_token", current.getString("refresh")), false);
                    save(result, current.getString("marker"), current.optBoolean("persist", true));
                } catch (Api.HttpError error) {
                    if (error.status == 401 || error.status == 403) vault.customerSession(null);
                    throw error;
                }
            }
            return api.request(PREFIX + operation, data, vault.customerSession().getString("access"));
        }
    }

    void changePassword(String password) throws Exception {
        synchronized (SESSIONS) {
            JSONObject result = call("password", proof("password").put("password", password));
            save(result, UUID.randomUUID().toString(), vault.customerSession().optBoolean("persist", true));
        }
    }

    JSONObject bootstrapProfiles() throws Exception {
        return call("bootstrap", proof("connect")).getJSONObject("profiles");
    }

    JSONObject connect(String carrier) throws Exception {
        return call("connect", proof("connect").put("carrier", carrier));
    }

    void logout() throws Exception {
        synchronized (SESSIONS) {
            try { call("logout", new JSONObject()); }
            finally { vault.customerSession(null); }
        }
    }
}
