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
}

