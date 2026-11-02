package za.co.topprivateplug;

import org.json.JSONArray;
import org.json.JSONObject;

/** A loopback control proxy can reach only the configured HTTPS account origin. */
final class TunnelConfig {
    static JSONObject control(JSONObject source, String origin, int port, boolean bootstrap) throws Exception {
        JSONObject config=new JSONObject(source.toString());
        JSONArray inputs=bootstrap?new JSONArray():config.getJSONArray("inbounds");
        inputs.put(new JSONObject(ControlPolicy.inbound(port)));
        config.put("inbounds",inputs);
        JSONArray rules=new JSONArray(ControlPolicy.rules(origin,bootstrap));
        if(!bootstrap) {
            JSONArray existing=config.getJSONObject("routing").getJSONArray("rules");
            for(int i=0;i<existing.length();i++) rules.put(existing.get(i));
        }
        config.put("routing",new JSONObject().put("domainStrategy","AsIs").put("rules",rules));
        return config;
    }
}

