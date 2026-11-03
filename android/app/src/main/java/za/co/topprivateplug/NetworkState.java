package za.co.topprivateplug;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;

final class NetworkState {
    static boolean available(Context context) {
        try {
            ConnectivityManager manager=context.getSystemService(ConnectivityManager.class);
            for(android.net.Network network:manager.getAllNetworks()) {
                NetworkCapabilities caps=manager.getNetworkCapabilities(network);
                if(caps!=null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN))return true;
            }
        } catch(Exception ignored) {}
        return false;
    }
    static boolean validated(Context context) {
        try {
            ConnectivityManager manager=context.getSystemService(ConnectivityManager.class);
            NetworkCapabilities caps=manager.getNetworkCapabilities(manager.getActiveNetwork());
            return caps!=null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
        } catch(Exception ignored) { return false; }
    }
}

