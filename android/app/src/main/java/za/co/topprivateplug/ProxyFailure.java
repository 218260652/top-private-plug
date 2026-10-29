package za.co.topprivateplug;

/** Fixed error codes only; never retain the diagnostic text or profile secrets. */
final class ProxyFailure extends Exception {
    final int status;
    ProxyFailure(int status) {
        super(status==429
            ? "The profile's upstream proxy is limiting connections (429). Wait 30 seconds, then retry. If this continues, ask your admin to check or replace the upstream proxy. Your saved access is unchanged."
            : "The profile's upstream proxy is unavailable (503). Wait 30 seconds, then retry. If this continues, ask your admin to check or replace the upstream proxy. Your saved access is unchanged.");
        this.status=status;
    }
    static int status(String diagnostic) {
        if(diagnostic==null)return 0;
        if(diagnostic.contains("Proxy responded with non 200 code: 429"))return 429;
        if(diagnostic.contains("Proxy responded with non 200 code: 503"))return 503;
        return 0;
    }
}
