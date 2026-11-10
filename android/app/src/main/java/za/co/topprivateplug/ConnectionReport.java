package za.co.topprivateplug;

import java.util.ArrayDeque;
import java.util.Locale;

/** In-memory diagnostics. Accept only fixed stages, routes and error categories. */
final class ConnectionReport {
    enum Stage {
        START, NO_SAVED_PROFILE, SAVED_PROFILE_START, SAVED_TUNNEL_HTTPS, SAVED_TUNNEL_HTTPS_OK, SAVED_TUNNEL_HTTPS_FAILED, ACCOUNT_VIA_TUNNEL, ACCOUNT_VIA_DIRECT, ACCOUNT_DIRECT_RETRY, ACCOUNT_CHALLENGE, DEVICE_PROOF, ACCOUNT_AUTHORIZATION,
        ENDPOINT_DNS_START, ENDPOINT_DNS_OK, ENDPOINT_DNS_FAILED, VPN_INTERFACE, NATIVE_START, TUNNEL_STARTED_UNVERIFIED, TRAFFIC_CHECK_COOLDOWN, TUNNEL_IP_HTTPS, TUNNEL_IP_HTTPS_OK, HTTP_UPSTREAM_ROUTE, DIRECT_ENDPOINT_ROUTE, DIRECT_ENDPOINT_RETRY, TUNNEL_HTTPS, TUNNEL_HTTPS_ALTERNATE, ACCOUNT_CHECK, ACCOUNT_CHECK_OK, TUNNEL_HTTPS_OK, TUNNEL_HTTPS_FAILED, CONNECTED,
        HEARTBEAT_RETRY, RECONNECT_SCHEDULED, RECONNECT_EXHAUSTED, CANCEL_OR_CLEANUP, CLEANUP_COMPLETE, WATCHDOG_TIMEOUT, ENGINE_LOAD_FAILED
    }
    enum ProbeFailure {
        TLS_CERTIFICATE, TLS_HANDSHAKE, DNS_LOOKUP, TCP_CONNECT, HTTPS_TIMEOUT, HTTPS_RESPONSE, UNKNOWN;

        static ProbeFailure classify(String message) {
            if (message == null) return UNKNOWN;
            String lower = message.toLowerCase(Locale.ROOT);
            if (lower.contains("x509:") || lower.contains("certificate verify failed")
                    || lower.contains("failed to verify certificate")) return TLS_CERTIFICATE;
            if (lower.contains("tls handshake") || lower.contains("remote error: tls:")) return TLS_HANDSHAKE;
            if (lower.contains("no such host") || lower.contains("failed to lookup")) return DNS_LOOKUP;
            if (lower.contains("dial tcp") || lower.contains("network is unreachable")) return TCP_CONNECT;
            if (lower.contains("deadline exceeded") || lower.contains("timeout")) return HTTPS_TIMEOUT;
            if (lower.contains("invalid status:")) return HTTPS_RESPONSE;
            return UNKNOWN;
        }

        Exception asException() {
            switch (this) {
                case TLS_CERTIFICATE:
                    return new java.security.cert.CertificateException(name());
                case TLS_HANDSHAKE:
                    return new javax.net.ssl.SSLHandshakeException(name());
                case DNS_LOOKUP:
                    return new java.net.UnknownHostException(name());
                case TCP_CONNECT:
                    return new java.net.ConnectException(name());
                case HTTPS_TIMEOUT:
                    return new java.net.SocketTimeoutException(name());
                default:
                    return new java.net.ProtocolException(name());
            }
        }
    }

    static synchronized void probeFailure(ProbeFailure failure) {
        append("XRAY_PROBE_" + failure.name());
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
                "/v1/profiles", "/v1/xray/heartbeat", "/v1/xray/disconnect",
                "/v2/customer/challenge", "/v2/customer/refresh", "/v2/customer/bootstrap", "/v2/customer/connect", "/v2/customer/heartbeat", "/v2/customer/disconnect"})
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
    static synchronized void trafficProbeFailed(boolean fixedIp, Throwable error) {
        append((fixedIp ? "TUNNEL_IP_HTTPS_FAILED " : "TUNNEL_HTTPS_FAILED ") + category(error));
    }
    static String category(Throwable error) {
        for (int i=0; error != null && i<8; i++, error=error.getCause()) {
            if (error instanceof ProxyFailure) return "UPSTREAM_PROXY_"+((ProxyFailure)error).status;
            if (error instanceof java.net.UnknownHostException) return "DNS_LOOKUP";
            if (error instanceof java.net.SocketTimeoutException) return "NETWORK_TIMEOUT";
            if (error instanceof java.security.cert.CertificateException) return "TLS_CERTIFICATE";
            if (error instanceof javax.net.ssl.SSLException) return "TLS_HANDSHAKE";
            if (error instanceof java.net.ConnectException) return "TCP_CONNECT";
            if (error instanceof java.io.EOFException) return "TRANSPORT_EOF";
            if (error instanceof java.net.ProtocolException) return "HTTP_PROTOCOL";
            if (error instanceof java.net.SocketException) return "SOCKET_CLOSED_OR_RESET";
            if (error instanceof java.io.InterruptedIOException || error instanceof InterruptedException) return "INTERRUPTED";
        }
        return "OTHER_ERROR";
    }
    static synchronized String snapshot() {
        StringBuilder report = new StringBuilder("Top Private Plug connection report\nEvents since app launch (oldest first; last 48).\n");
        report.append("Connection stages and HTTP status codes only.\n");
        if (events.isEmpty()) report.append("No connection events yet. Retry the account check or connection first.\n");
        for (String event : events) report.append(event).append('\n');
        return report.toString();
    }
}




