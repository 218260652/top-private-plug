package za.co.topprivateplug;

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

    static void useDirectEndpoint(JSONObject config) throws Exception {
        JSONObject stream = config.getJSONArray("outbounds").getJSONObject(0).getJSONObject("streamSettings");
        stream.getJSONObject("sockopt").remove("dialerProxy");
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

