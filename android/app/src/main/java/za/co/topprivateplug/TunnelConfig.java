package za.co.topprivateplug;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Adds the loopback account-control proxy, keeps the imported profile routing, and
 * fails IPv6 fast. Supplier VLESS/Trojan servers carry IPv4 only, so routing AAAA
 * traffic into the tunnel and letting it hang is what makes MTN/Telkom look
 * connected while pages never load.
 */
final class TunnelConfig {
    static JSONObject control(JSONObject source, String origin, int port, boolean bootstrap) throws Exception {
        JSONObject config=new JSONObject(source.toString());
        String tunnel=outboundTag(config);
        JSONArray inputs=bootstrap?new JSONArray():config.getJSONArray("inbounds");
        inputs.put(new JSONObject(ControlPolicy.inbound(port)));
        config.put("inbounds",inputs);
        JSONArray rules=new JSONArray();
        JSONArray control=new JSONArray(ControlPolicy.rules(origin,bootstrap,tunnel));
        for(int i=0;i<control.length();i++) rules.put(control.get(i));
        if(!bootstrap) {
            // Ahead of the profile rules, which end in a catch-all send to the
            // tunnel. Android still owns the ::/0 route so nothing leaks to the
            // carrier, but IPv6 destinations now fail immediately and apps fall
            // back to IPv4 instead of stalling.
            rules.put(new JSONObject().put("type","field")
                .put("inboundTag",new JSONArray().put("tun-inbound"))
                .put("ip",new JSONArray().put("::/0")).put("outboundTag","block"));
            JSONObject routing=config.optJSONObject("routing");
            JSONArray existing=routing==null?null:routing.optJSONArray("rules");
            if(existing!=null) for(int i=0;i<existing.length();i++) rules.put(existing.get(i));
        }
        config.put("routing",new JSONObject().put("domainStrategy","AsIs").put("rules",rules));
        return config;
    }
    /** The imported outbound keeps the historical "trojan" tag even for VLESS. */
    private static String outboundTag(JSONObject config) {
        JSONArray outbounds=config.optJSONArray("outbounds");
        if(outbounds!=null) for(int i=0;i<outbounds.length();i++) {
            JSONObject outbound=outbounds.optJSONObject(i);
            if(outbound==null) continue;
            String protocol=outbound.optString("protocol");
            if("vless".equals(protocol)||"trojan".equals(protocol)) {
                String tag=outbound.optString("tag");
                return tag.isEmpty()?"trojan":tag;
            }
        }
        return "trojan";
    }
}
