package za.co.topprivateplug;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import javax.net.ssl.HttpsURLConnection;

final class Api {
    interface Progress { void stage(String message) throws Exception; }
    private final Vault vault;
    Api(Vault vault) { this.vault = vault; }
    JSONObject request(String path, JSONObject data, boolean authenticated) throws Exception {
        String endpoint = vault.endpoint();
        if (endpoint.isEmpty()) throw new Exception("Set your service address in Settings first.");
        URL url = new URL(endpoint + path);
        if (!"https".equals(url.getProtocol())) throw new Exception("The service address must use HTTPS.");
        HttpsURLConnection connection = (HttpsURLConnection)url.openConnection();
        connection.setConnectTimeout(12000); connection.setReadTimeout(45000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("X-TPP-Engines", "xray");
        connection.setRequestProperty("X-TPP-Features", "legacy-tls-test-v1");
        if (authenticated) connection.setRequestProperty("Authorization", "Bearer " + vault.token());
        try {
            if (data != null) {
                connection.setRequestMethod("POST"); connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json");
                byte[] bytes = data.toString().getBytes("UTF-8"); connection.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream output = connection.getOutputStream()) { output.write(bytes); }
            }
            int status = connection.getResponseCode();
            InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            if (stream == null) throw new Exception("The service did not return a response.");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = stream) {
                byte[] buffer = new byte[4096]; int size;
                while ((size = input.read(buffer)) != -1) { bytes.write(buffer, 0, size); if (bytes.size() > 1024 * 1024) throw new Exception("Service response is too large."); }
            }
            JSONObject result = new JSONObject(bytes.toString("UTF-8"));
            if (status < 200 || status >= 300) throw new Exception(result.optString("error", "Service request failed."));
            return result;
        } finally { connection.disconnect(); }
    }
    JSONObject proof(String purpose) throws Exception {
        return proof(purpose, null);
    }
    JSONObject proof(String purpose, Progress progress) throws Exception {
        if (progress != null) progress.stage("Contacting account service for a connection challenge");
        String publicKey = DeviceKey.publicKey();
        JSONObject challenge = request("/v1/challenge", new JSONObject().put("public_key", publicKey).put("purpose", purpose), false);
        if (progress != null) progress.stage("Signing the device challenge");
        return new JSONObject().put("public_key", publicKey).put("challenge_id", challenge.getString("id"))
            .put("signature", DeviceKey.sign(challenge.getString("message")));
    }
    JSONObject activate(String code) throws Exception {
        JSONObject result = request("/v1/activate", proof("activate").put("code", code.trim()), false);
        vault.token(result.getString("token")); return result.getJSONObject("account");
    }
    JSONObject connect(String profile) throws Exception { return request("/v1/connect", proof("connect").put("profile_id", profile), true); }
    JSONObject connect(String profile, Progress progress) throws Exception {
        JSONObject data = proof("connect", progress).put("profile_id", profile);
        progress.stage("Authorizing account and downloading the connection profile");
        return request("/v1/connect", data, true);
    }
}



