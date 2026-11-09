package za.co.topprivateplug;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;

final class NetworkState {
    static boolean validated(Context context) {
        try {
            ConnectivityManager manager=context.getSystemService(ConnectivityManager.class);
            NetworkCapabilities caps=manager.getNetworkCapabilities(manager.getActiveNetwork());
            return caps!=null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
        } catch(Exception ignored) { return false; }
    }

    /**
     * Whether an account request is worth attempting. Android only sets VALIDATED
     * after its own probe succeeds, which MTN and Telkom mobile APNs often delay or
     * suppress (proxied/captive APN, carrier DNS interception). Requiring it locked
     * those customers out of saving or refreshing a profile on mobile data, so a
     * usable INTERNET capability is enough to try; the request itself still fails
     * closed and reports the reason.
     */
    static boolean usable(Context context) {
        try {
            ConnectivityManager manager=context.getSystemService(ConnectivityManager.class);
            NetworkCapabilities caps=manager.getNetworkCapabilities(manager.getActiveNetwork());
            return caps!=null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
        } catch(Exception ignored) { return false; }
    }
}
