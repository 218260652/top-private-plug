package za.co.topprivateplug;

import java.io.File;
import libv2ray.CoreCallbackHandler;
import libv2ray.CoreController;
import libv2ray.Libv2ray;

/** The pinned native core owns a duplicate of Android's TUN descriptor. */
final class XrayEngine {
    private final CoreController core;
    XrayEngine(File directory) {
        Libv2ray.initCoreEnv(directory.getAbsolutePath(), "");
        core = Libv2ray.newCoreController(new CoreCallbackHandler() {
            @Override public long startup() { return 0; }
            @Override public long shutdown() { return 0; }
            @Override public long onEmitStatus(long code, String text) { return 0; }
        });
    }
    void start(String config, int fd) throws Exception { core.startLoop(config, fd); }
    long probe(String url) throws Exception { return core.measureDelay(url); }
    String traffic() { return core.queryAllOutboundTrafficStats(); }
    boolean running() { return core.getIsRunning(); }
    void stop() { try { core.stopLoop(); } catch (Exception ignored) {} }
}
