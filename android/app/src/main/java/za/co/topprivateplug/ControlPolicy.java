package za.co.topprivateplug;

import java.net.URI;

/** Pure policy generation, exercised independently of Android and by native Xray fixtures. */
final class ControlPolicy {
    static String rules(String origin, boolean bootstrap) throws Exception {
        URI uri=new URI(origin);
        if(!"https".equals(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null || uri.getQuery()!=null || uri.getFragment()!=null
            || (!uri.getPath().isEmpty() && !"/".equals(uri.getPath()))) throw new Exception("Invalid account service origin.");
        int port=uri.getPort()<0?443:uri.getPort();
        if(port<1||port>65535) throw new Exception("Invalid account service port.");
        String host=uri.getHost();
        if(host.startsWith("[")&&host.endsWith("]"))host=host.substring(1,host.length()-1);
        boolean literal=host.indexOf(':')>=0||host.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+");
        String target=literal?"\"ip\":[\""+host+"\"]":"\"domain\":[\"full:"+host+"\"]";
        return "[{\"type\":\"field\",\"inboundTag\":[\"admin-control\"],"+target+
            ",\"port\":\""+port+"\",\"network\":\"tcp\",\"outboundTag\":\"trojan\"},"+
            (bootstrap?"":"{\"type\":\"field\",\"inboundTag\":[\"admin-control\"],\"domain\":[\"full:top-private-plug-downloads.ramashiaemily.chatgpt.site\"],\"port\":\"443\",\"network\":\"tcp\",\"outboundTag\":\"trojan\"},")+
            "{\"type\":\"field\",\"inboundTag\":[\"admin-control\"],\"network\":\"tcp,udp\",\"outboundTag\":\"block\"}"+
            (bootstrap?",{\"type\":\"field\",\"network\":\"tcp,udp\",\"outboundTag\":\"block\"}":"")+"]";
    }
    static String inbound(int port) throws Exception {
        if(port<1||port>65535)throw new Exception("Invalid local control port.");
        return "{\"tag\":\"admin-control\",\"listen\":\"127.0.0.1\",\"port\":"+port+
            ",\"protocol\":\"http\",\"settings\":{}}";
    }
}


