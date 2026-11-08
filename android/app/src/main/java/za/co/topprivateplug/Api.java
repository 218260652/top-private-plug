package za.co.topprivateplug;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.net.Proxy;
import java.net.InetSocketAddress;
import javax.net.ssl.HttpsURLConnection;

final class Api {
    static final class HttpError extends Exception {
        final int status;
        final boolean authenticated;
        HttpError(int status, String message, boolean authenticated) { super(message); this.status=status; this.authenticated=authenticated; }
    }
    interface Progress { void stage(String message) throws Exception; }
    private static volatile ControlRoute tunnelRoute;
    static final class ControlRoute {
        final String endpoint; final Proxy proxy; final Runnable beforeRequest;
        ControlRoute(String endpoint,int port,Runnable beforeRequest) { this.beforeRequest=beforeRequest;this.endpoint=endpoint; proxy=new Proxy(Proxy.Type.HTTP,new InetSocketAddress("127.0.0.1",port)); }
    }
    static void throughTunnel(String endpoint,int port) { throughTunnel(endpoint,port,null); }
    static void throughTunnel(String endpoint,int port,Runnable beforeRequest) { tunnelRoute=new ControlRoute(endpoint,port,beforeRequest); }
    static Proxy updateProxy() { ControlRoute route=tunnelRoute; return route==null?null:route.proxy; }
    static void clearTunnel() { tunnelRoute=null; }
    private final Vault vault;
    Api(Vault vault) { this.vault = vault; }
    JSONObject request(String path, JSONObject data, boolean authenticated) throws Exception {
        return request(path, data, authenticated ? vault.token() : null);
    }
    JSONObject request(String path, JSONObject data, String bearer) throws Exception {
        boolean authenticated = bearer != null;
        String endpoint = vault.endpoint();
        if (endpoint.isEmpty()) throw new Exception("Set your service address in Settings first.");
        URL url = new URL(endpoint + path);
        if (!"https".equals(url.getProtocol())) throw new Exception("The service address must use HTTPS.");
        ControlRoute route=tunnelRoute;
        if(route!=null && !route.endpoint.equals(endpoint)) throw new Exception("Disconnect before changing the account service.");
        if(route!=null && route.beforeRequest!=null)route.beforeRequest.run();
        HttpsURLConnection connection = (HttpsURLConnection)(route==null?url.openConnection():url.openConnection(route.proxy));
        boolean heartbeat = "/v1/xray/heartbeat".equals(path) || "/v1/xray/disconnect".equals(path)
            || "/v2/customer/heartbeat".equals(path) || "/v2/customer/disconnect".equals(path);
        connection.setConnectTimeout(heartbeat ? 5000 : 12000);
        connection.setReadTimeout(heartbeat ? 10000 : 45000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Accept", "application/json");
        // Android pools by HTTPS origin and explicit Proxy route. Keep a fully
        // consumed account connection reusable between challenge and authorization.
        connection.setRequestProperty("X-TPP-Engines", "xray");
        connection.setRequestProperty("X-TPP-Features", "legacy-tls-test-v1");
        if (authenticated) connection.setRequestProperty("Authorization", "Bearer " + bearer);
        ConnectionReport.request(path, 0, route!=null);
        boolean consumed=false;
        try {
            if (data != null) {
                connection.setRequestMethod("POST"); connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json");
                byte[] bytes = data.toString().getBytes("UTF-8"); connection.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream output = connection.getOutputStream()) { output.write(bytes); }
            }
            int status = connection.getResponseCode();
            ConnectionReport.request(path, status, route!=null);
            InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            if (stream == null) throw new Exception("The service did not return a response.");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = stream) {
                byte[] buffer = new byte[4096]; int size;
                while ((size = input.read(buffer)) != -1) { bytes.write(buffer, 0, size); if (bytes.size() > 1024 * 1024) throw new Exception("Service response is too large."); }
            }
            consumed=true;
            JSONObject result = new JSONObject(bytes.toString("UTF-8"));
            if (status < 200 || status >= 300) throw new HttpError(status, path.startsWith("/v2/customer/") ?
                result.optString("error", CustomerMessage.forStatus(status)) : CustomerMessage.forStatus(status), authenticated);
            return result;
        } catch (javax.net.ssl.SSLException error) {
            ConnectionReport.failure(path, error);
            throw new Exception("The account HTTPS connection was interrupted or could not be verified. Open Connection report for the tunnel or certificate error. Your saved access has not been removed.", error);
        } catch (java.io.IOException error) {
            ConnectionReport.failure(path, error);
            throw new Exception("Cannot reach the account service (" + ConnectionReport.category(error) + "). Account verification could not complete. Open Connection report for details. Your saved access has not been removed.", error);
        } finally { if(!consumed)connection.disconnect(); }
    }
    JSONObject proof(String purpose) throws Exception {
        return proof(purpose, null);
    }
    JSONObject proof(String purpose, Progress progress) throws Exception {
        ConnectionReport.stage(ConnectionReport.Stage.ACCOUNT_CHALLENGE);
        if (progress != null) progress.stage("Contacting account service for a connection challenge");
        String publicKey = DeviceKey.publicKey();
        JSONObject challenge = request("/v1/challenge", new JSONObject().put("public_key", publicKey).put("purpose", purpose), false);
        if (progress != null) progress.stage("Signing the device challenge");
        ConnectionReport.stage(ConnectionReport.Stage.DEVICE_PROOF);
        return new JSONObject().put("public_key", publicKey).put("challenge_id", challenge.getString("id"))
            .put("signature", DeviceKey.sign(challenge.getString("message")));
    }
    JSONObject activate(String code) throws Exception {
        JSONObject result = request("/v1/activate", proof("activate").put("code", code.trim()), false);
        vault.token(result.getString("token")); return result.getJSONObject("account");
    }
    JSONObject connect(String profile) throws Exception { return request("/v1/connect", proof("connect").put("profile_id", profile), true); }
    void prepareProfiles(org.json.JSONArray profiles) throws Exception { prepareProfiles(profiles,false); }
    void prepareProfiles(org.json.JSONArray profiles, boolean replace) throws Exception {
        final String accessToken=vault.token(), origin=vault.endpoint();
        for(int i=0;i<profiles.length();i++) {
            JSONObject profile=profiles.getJSONObject(i);
            String id=profile.getString("id");
            if(!"xray".equals(profile.optString("engine")) || (!replace && vault.bootstrap(id)!=null)) continue;
            if(!accessToken.equals(vault.token()) || !origin.equals(vault.endpoint())) throw new Exception("Saved access changed. Retry saving profiles.");
            // Use the existing device-proof API so older admin servers also work.
            // No native engine or TUN is opened; release the temporary lease immediately.
            JSONObject result=request("/v1/connect",proof("connect").put("profile_id",id),true);
            try {
                if(!"xray".equals(result.optString("engine"))) throw new Exception("Unsupported connection profile.");
                vault.bootstrap(id,result,accessToken,origin);
            } finally {
                if(accessToken.equals(vault.token()) && origin.equals(vault.endpoint()))
                    request("/v1/xray/disconnect",new JSONObject().put("lease",result.getString("lease")),true);
            }
        }
    }
    JSONObject connect(String profile, Progress progress) throws Exception {
        String accessToken=vault.token(), origin=vault.endpoint();
        JSONObject data = proof("connect", progress).put("profile_id", profile);
        progress.stage("Authorizing account and downloading the connection profile");
        ConnectionReport.stage(ConnectionReport.Stage.ACCOUNT_AUTHORIZATION);
        JSONObject result=request("/v1/connect", data, true);
        if(!accessToken.equals(vault.token()) || !origin.equals(vault.endpoint())) throw new Exception("Saved access changed during connection. Retry.");
        if("xray".equals(result.optString("engine"))) vault.bootstrap(profile,result,accessToken,origin);
        return result;
    }
}







