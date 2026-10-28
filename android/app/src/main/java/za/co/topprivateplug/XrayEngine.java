package za.co.topprivateplug;

import java.io.File;
import libv2ray.CoreCallbackHandler;
import libv2ray.CoreController;
import libv2ray.Libv2ray;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.json.JSONArray;
import org.json.JSONObject;

/** The pinned native core owns a duplicate of Android's TUN descriptor. */
final class XrayEngine {
    private final CoreController core;
    private volatile String warning = "";
    private final List<String> secrets = new ArrayList<>();
    XrayEngine(File directory) {
        Libv2ray.initCoreEnv(directory.getAbsolutePath(), "");
        core = Libv2ray.newCoreController(new CoreCallbackHandler() {
            @Override public long startup() { return 0; }
            @Override public long shutdown() { return 0; }
            @Override public long onEmitStatus(long code, String text) {
                if (code == 100 && text != null) {
                    String lower = text.toLowerCase(Locale.ROOT);
                    if (lower.contains("failed") || lower.contains("error") || lower.contains("eof") || lower.contains("rejected")) {
                        warning = redact(text);
                    }
                }
                return 0;
            }
        });
    }
    private String redact(String text) {
        for (String secret : secrets) if (!secret.isEmpty()) text = text.replace(secret, "[redacted]");
        text = text.replaceAll("(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "[redacted UUID]");
        text = text.replace('\n', ' ').replace('\r', ' ');
        return text.length() > 800 ? text.substring(0, 800) : text;
    }
    private void collectSecrets(Object value) throws Exception {
        if (value instanceof JSONObject) {
            JSONObject object = (JSONObject)value;
            java.util.Iterator<String> keys = object.keys();
            while (keys.hasNext()) {
                String key = keys.next(); Object child = object.get(key);
                if (("id".equals(key) || "password".equals(key) || "user".equals(key) ||
                    "X-iorg-bsid".equalsIgnoreCase(key) || "Proxy-Authorization".equalsIgnoreCase(key)) && child instanceof String) secrets.add((String)child);
                else collectSecrets(child);
            }
        } else if (value instanceof JSONArray) {
            JSONArray array = (JSONArray)value;
            for (int i = 0; i < array.length(); i++) collectSecrets(array.get(i));
        }
    }
    void start(String config, int fd) throws Exception {
        JSONObject parsed = new JSONObject(config);
        collectSecrets(parsed);
        parsed.put("log", new JSONObject().put("loglevel", "info"));
        core.startLoop(parsed.toString(), fd);
    }
    String diagnostic() { return warning; }
    long probe(String url) throws Exception { return core.measureDelay(url); }
    String traffic() { return core.queryAllOutboundTrafficStats(); }
    boolean running() { return core.getIsRunning(); }
    void stop() { try { core.stopLoop(); } catch (Exception ignored) {} }
}

