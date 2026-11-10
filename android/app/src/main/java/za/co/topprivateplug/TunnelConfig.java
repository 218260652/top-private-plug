package za.co.topprivateplug;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import java.net.UnknownHostException;
import java.util.Iterator;
import org.json.JSONArray;
import org.json.JSONObject;

/** A loopback control proxy can reach only the configured HTTPS account origin. */
final class TunnelConfig {
    // The backend normalizes a staged HTTP detour to this named dialer.
    static boolean hasHttpUpstream(JSONObject config) throws Exception {
        JSONObject stream = config.getJSONArray("outbounds").getJSONObject(0).optJSONObject("streamSettings");
        JSONObject sockets = stream == null ? null : stream.optJSONObject("sockopt");
        return sockets != null && "http-upstream".equals(sockets.optString("dialerProxy"));
    }

    static void resolveDirectEndpoint(JSONObject config, Context context) throws Exception {
        JSONObject outbound = config.getJSONArray("outbounds").getJSONObject(0);
        JSONObject stream = outbound.getJSONObject("streamSettings");
        JSONObject endpoint = outbound.getJSONObject("settings")
            .getJSONArray("vless".equals(outbound.getString("protocol")) ? "vnext" : "servers")
            .getJSONObject(0);
        String host = endpoint.getString("address");
        if (host.indexOf(':') >= 0 || host.matches("[0-9]+[.][0-9]+[.][0-9]+[.][0-9]+")) return;

        ConnectionReport.stage(ConnectionReport.Stage.ENDPOINT_DNS_START);
        ConnectivityManager connectivity = context.getSystemService(ConnectivityManager.class);
        Network network = connectivity.getActiveNetwork();
        String address;
        try {
            if (network == null) throw new UnknownHostException("No active network for endpoint DNS");
            address = network.getAllByName(host)[0].getHostAddress();
        } catch (UnknownHostException error) {
            ConnectionReport.stage(ConnectionReport.Stage.ENDPOINT_DNS_FAILED);
            throw error;
        }

        // Change the dial address only. Keep the hostname for certificate verification and HTTP routing.
        JSONObject tls = stream.getJSONObject("tlsSettings");
        if (tls.optString("serverName").isEmpty()) tls.put("serverName", host);
        if ("ws".equals(stream.optString("network"))) {
            JSONObject ws = stream.getJSONObject("wsSettings");
            JSONObject headers = ws.getJSONObject("headers");
            boolean explicitHost = !ws.optString("host").isEmpty();
            for (Iterator<String> keys = headers.keys(); keys.hasNext();) {
                if ("host".equalsIgnoreCase(keys.next())) explicitHost = true;
            }
            if (!explicitHost) {
                int port = endpoint.getInt("port");
                headers.put("Host", port == 443 ? host : host + ":" + port);
            }
        }
        endpoint.put("address", address);
        ConnectionReport.stage(ConnectionReport.Stage.ENDPOINT_DNS_OK);
    }

    static JSONObject control(JSONObject source, String origin, int port, boolean bootstrap) throws Exception {
        return control(source, origin, port, bootstrap, false);
    }

    static JSONObject control(JSONObject source, String origin, int port, boolean bootstrap, boolean probe) throws Exception {
        JSONObject config=new JSONObject(source.toString());
        JSONArray inputs=bootstrap?new JSONArray():config.getJSONArray("inbounds");
        inputs.put(new JSONObject(ControlPolicy.inbound(port)));
        config.put("inbounds",inputs);
        JSONArray rules=new JSONArray(ControlPolicy.rules(origin,bootstrap,probe));
        if(!bootstrap) {
            JSONArray existing=config.getJSONObject("routing").getJSONArray("rules");
            for(int i=0;i<existing.length();i++) rules.put(existing.get(i));
        }
        config.put("routing",new JSONObject().put("domainStrategy","AsIs").put("rules",rules));
        return config;
    }
}

