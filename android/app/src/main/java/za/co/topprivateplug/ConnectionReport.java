package za.co.topprivateplug;

import java.util.ArrayDeque;
import java.util.Locale;

/** In-memory diagnostics. Accept only fixed stages, routes and error categories. */
final class ConnectionReport {
    enum Stage {
        START, NO_SAVED_PROFILE, SAVED_PROFILE_START, ACCOUNT_VIA_TUNNEL, ACCOUNT_CHALLENGE, DEVICE_PROOF, ACCOUNT_AUTHORIZATION,
        VPN_INTERFACE, NATIVE_START, TUNNEL_HTTPS, CONNECTED,
        CANCEL_OR_CLEANUP, CLEANUP_COMPLETE, WATCHDOG_TIMEOUT, ENGINE_LOAD_FAILED
    }
    private static final ArrayDeque<String> events = new ArrayDeque<>();
    private static final long origin = System.nanoTime();
    static synchronized void stage(Stage stage) { append(stage.name()); }
    private static void append(String event) {
        if (events.size() == 48) events.removeFirst();
        events.addLast(String.format(Locale.ROOT, "+%.1fs %s", (System.nanoTime()-origin)/1e9, event));
    }
    private static String route(String path) {
        for (String allowed : new String[]{"/v1/challenge", "/v1/connect", "/v1/activate", "/v1/status",
                "/v1/profiles", "/v1/xray/heartbeat", "/v1/xray/disconnect"})
            if (allowed.equals(path)) return allowed;
        return "other account request";
    }
    static synchronized void request(String path, int status) { request(path,status,false); }
    static synchronized void request(String path, int status, boolean tunnel) {
        append((tunnel?"TUNNEL_ACCOUNT ":"DIRECT_ACCOUNT ") + route(path) + (status == 0 ? " START" : " HTTP_" + status));
    }
    static synchronized void failure(String path, Throwable error) {
        append("FAILED " + (path == null ? "tunnel stage" : route(path)) + " " + category(error));
    }
    static String category(Throwable error) {
        for (int i=0; error != null && i<8; i++, error=error.getCause()) {
            if (error instanceof ProxyFailure) return "UPSTREAM_PROXY_"+((ProxyFailure)error).status;
            if (error instanceof java.net.UnknownHostException) return "DNS_LOOKUP";
            if (error instanceof java.net.SocketTimeoutException) return "NETWORK_TIMEOUT";
            if (error instanceof javax.net.ssl.SSLException) return "TLS_HANDSHAKE";
            if (error instanceof java.net.ConnectException) return "TCP_CONNECT";
            if (error instanceof java.io.InterruptedIOException || error instanceof InterruptedException) return "INTERRUPTED";
        }
        return "OTHER_ERROR";
    }
    static synchronized String snapshot() {
        StringBuilder report = new StringBuilder("Top private Plug 0.1.14 pilot\nEvents since app launch (oldest first; last 48).\n");
        report.append("Saved-profile startup verifies the account through VLESS/Trojan before enabling the VPN.\n");
        if (events.isEmpty()) report.append("No connection events yet. Retry the account check or connection first.\n");
        for (String event : events) report.append(event).append('\n');
        return report.toString();
    }
}


