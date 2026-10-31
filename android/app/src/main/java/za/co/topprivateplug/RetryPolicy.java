package za.co.topprivateplug;

/** Bounded transport recovery; authorization and certificate errors stay terminal. */
final class RetryPolicy {
    static final int MAX_RETRIES = 5;
    static final class TransportFailure extends Exception {
        TransportFailure(String message) { super(message); }
    }
    static long delayMillis(int attempt, boolean proxy, boolean hadLease) {
        long delay = Math.min(60000L, 2000L << Math.max(0, Math.min(attempt - 1, 5)));
        // Respect the proxy cooldown; don't create overlapping account leases.
        return Math.max(delay, hadLease ? 35000L : proxy ? 30000L : 0L);
    }
    static boolean transientFailure(Throwable error) {
        Throwable cause=error;
        for (int i=0; cause!=null && i<8; i++,cause=cause.getCause()) {
            if (cause instanceof javax.net.ssl.SSLHandshakeException || cause instanceof javax.net.ssl.SSLPeerUnverifiedException
                || cause instanceof java.security.cert.CertificateException) return false;
        }
        for (int i=0; error!=null && i<8; i++,error=error.getCause()) {
            if (error instanceof Api.HttpError) {
                int status=((Api.HttpError)error).status;
                return status==408 || status==429 || status==500 || status==502 || status==503 || status==504;
            }
            if (error instanceof ProxyFailure) return ((ProxyFailure)error).status==429 || ((ProxyFailure)error).status==503;
            if (error instanceof javax.net.ssl.SSLHandshakeException || error instanceof javax.net.ssl.SSLPeerUnverifiedException
                || error instanceof java.security.cert.CertificateException) return false;
            if (error instanceof java.io.InterruptedIOException && !(error instanceof java.net.SocketTimeoutException)) return false;
            if (error instanceof InterruptedException) return false;
            if (error instanceof java.io.IOException || error instanceof TransportFailure) return true;
        }
        return false;
    }
}
