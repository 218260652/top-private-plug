package za.co.topprivateplug;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.net.VpnService;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import android.os.Handler;
import android.os.Looper;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONObject;

public final class TunnelService extends VpnService {
    public static volatile String state = "Disconnected";
    public static volatile String detail = "";
    public static volatile long uploaded, downloaded, latency = -1;
    public static volatile long connectedAt;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private volatile ParcelFileDescriptor tun;
    private Thread worker, pinger;
    private volatile boolean foreground;
    private final AtomicBoolean stopping = new AtomicBoolean(false);
    private final Handler main = new Handler(Looper.getMainLooper());
    private volatile XrayEngine xray;
    private final Object xrayLock = new Object();
    private volatile long leaseDeadline;
    private String xrayLease;
    private int controlPort;
    private volatile String phase = "Starting VPN service";
    private volatile boolean reconnectAllowed, retryFailure, proxyFailure, retryPending, hadLease, leaseReleased;
    private volatile int retryAttempt;
    private String activeProfile, accessToken, accountOrigin;
    private Runnable retryTask;
    private android.net.ConnectivityManager connectivity;
    private android.net.ConnectivityManager.NetworkCallback networkCallback;

    boolean underlyingNetworkReady() { return NetworkState.available(this); }
    @Override public void onCreate() {
        super.onCreate();
        connectivity = getSystemService(android.net.ConnectivityManager.class);
        networkCallback = new android.net.ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(android.net.Network network) {
                ConnectionReport.stage(ConnectionReport.Stage.NETWORK_AVAILABLE);
                // A previously authorized lease still needs the legacy cooldown.
                // Never accelerate a proxy's rate-limit backoff.
                if(retryPending && retryTask != null && (!hadLease || leaseReleased) && !proxyFailure) {
                    main.removeCallbacks(retryTask); main.post(retryTask);
                }
            }
            @Override public void onLost(android.net.Network network) {
                ConnectionReport.stage(ConnectionReport.Stage.NETWORK_LOST);
            }
        };
        try {
            android.net.NetworkRequest request = new android.net.NetworkRequest.Builder()
                .addCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .addCapability(android.net.NetworkCapabilities.NET_CAPABILITY_NOT_VPN).build();
            connectivity.registerNetworkCallback(request, networkCallback, main);
        } catch (RuntimeException unavailable) { networkCallback = null; }
    }

    private void requestStop() {
        ConnectionReport.stage(ConnectionReport.Stage.STOP_REQUESTED);
        reconnectAllowed = false;
        retryPending = false;
        if (retryTask != null) main.removeCallbacks(retryTask);
        stopTunnel();
    }

    private void beginAttempt() {
        if (!reconnectAllowed || VpnService.prepare(this) != null) { requestStop(); return; }
        running.set(true);
        retryFailure = proxyFailure = hadLease = leaseReleased = false;
        state = retryAttempt == 0 ? "Connecting" : "Reconnecting";
        detail = retryAttempt == 0 ? "Starting VPN service…" : "Reconnecting…";
        ConnectionReport.stage(ConnectionReport.Stage.START);
        showNotification(detail);
        worker = new Thread(() -> runTunnel(activeProfile), "tpp-tunnel");
        worker.start();
    }

    private void onCleanupComplete() {
        stopping.set(false);
        ConnectionReport.stage(ConnectionReport.Stage.CLEANUP_COMPLETE);
        Vault vault = new Vault(this);
        boolean sameAccess = accessToken != null && !accessToken.isEmpty()
            && accessToken.equals(vault.token()) && accountOrigin.equals(vault.endpoint());
        if (reconnectAllowed && retryFailure && sameAccess) {
            retryAttempt = RetryPolicy.nextAttempt(retryAttempt);
            long delay = RetryPolicy.delayMillis(retryAttempt, proxyFailure, hadLease && !leaseReleased);
            state = "Reconnecting";
            detail = "Connection interrupted. Reconnecting automatically. Tap Cancel to stop.";
            retryPending = true;
            ConnectionReport.stage(ConnectionReport.Stage.RECONNECT_SCHEDULED);
            showNotification(detail);
            retryTask = () -> {
                Vault current = new Vault(this);
                if (!reconnectAllowed || !accessToken.equals(current.token()) || !accountOrigin.equals(current.endpoint())) {
                    requestStop(); return;
                }
                if(!underlyingNetworkReady()) {
                    ConnectionReport.stage(ConnectionReport.Stage.NETWORK_WAIT);
                    main.postDelayed(retryTask, 5000); return;
                }
                retryPending = false;
                beginAttempt();
            };
            main.postDelayed(retryTask, delay);
            return;
        }
        reconnectAllowed = false;
        stopping.set(true);
        if (foreground) { stopForeground(STOP_FOREGROUND_REMOVE); foreground = false; }
        state = "Disconnected";
        stopSelf();
    }

    private synchronized void progress(String message) throws Exception {
        if (!running.get()) throw new Exception("Connection cancelled.");
        phase = message;
        detail = "Preparing your secure connection…";
        showNotification(detail);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) { requestStop(); return START_NOT_STICKY; }
        if (intent == null) { stopSelf(startId); return START_NOT_STICKY; }
        if (stopping.get() || retryPending || (worker != null && worker.isAlive()) || running.get()) return START_NOT_STICKY;
        if (VpnService.prepare(this) != null) { stopSelf(); return START_NOT_STICKY; }
        Vault vault = new Vault(this);
        activeProfile = intent.getStringExtra("profile_id");
        accessToken = vault.token(); accountOrigin = vault.endpoint();
        retryAttempt = 0; reconnectAllowed = true;
        beginAttempt();
        return START_NOT_STICKY;
    }
    private void showNotification(String text) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("vpn", "VPN connection", NotificationManager.IMPORTANCE_LOW));
        PendingIntent activity = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, TunnelService.class).setAction("STOP"), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(this, "vpn").setSmallIcon(za.co.topprivateplug.R.drawable.ic_launcher)
            .setContentTitle("Top private Plug").setContentText(text).setContentIntent(activity).setOngoing(true)
            .addAction(new Notification.Action.Builder(null, "Disconnect", stop).build()).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(10, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED);
        else startForeground(10, notification);
        foreground = true;
    }
    private void runTunnel(String profileId) {
        synchronized (this) {
            if (!running.get()) return;
            state = retryAttempt == 0 ? "Connecting" : "Reconnecting"; detail = "Starting VPN service…"; uploaded = downloaded = 0; latency = -1;
        }
        phase = "Starting VPN service";
        xrayLease = null;
        leaseDeadline = android.os.SystemClock.elapsedRealtime() + 75000;
        pinger = new Thread(() -> {
            while (running.get()) {
                if (android.os.SystemClock.elapsedRealtime() >= leaseDeadline) {
                    ConnectionReport.stage(ConnectionReport.Stage.WATCHDOG_TIMEOUT);
                    detail = !"Connected".equals(state)
                        ? "The connection took too long. Please try again."
                        : "Account check timed out. Reconnect when the service is reachable.";
                    // Publish failure before cleanup, including if native startup is blocked.
                    retryFailure = true;
                    stopTunnel(); return;
                }
                try { Thread.sleep(500); } catch (InterruptedException ignored) { return; }
            }
        }, "tpp-xray-watchdog"); pinger.start();
        try {
            if (profileId == null) throw new Exception("Choose a connection profile.");
            Vault vault=new Vault(this);
            Api api = new Api(vault);
            try(java.net.ServerSocket reservation=new java.net.ServerSocket(0,1,java.net.InetAddress.getByName("127.0.0.1"))) {
                controlPort=reservation.getLocalPort();
            }
            JSONObject saved=vault.bootstrap(profileId);
            if(saved!=null) {
                progress("Starting saved VLESS or Trojan connection before account verification");
                ConnectionReport.stage(ConnectionReport.Stage.SAVED_PROFILE_START);
                synchronized(xrayLock) {
                    if(!running.get()) return;
                    xray=new XrayEngine(getFilesDir());
                    // No TUN inbound or Android VPN interface exists at this stage.
                    // Only the loopback account proxy is exposed; all other targets are blocked.
                    xray.start(TunnelConfig.control(saved.getJSONObject("config"),vault.endpoint(),controlPort,true).toString(),0);
                    Api.throughTunnel(vault.endpoint(),controlPort,xray::clearUpstreamStatus);
                }
                ConnectionReport.stage(ConnectionReport.Stage.ACCOUNT_VIA_TUNNEL);
            } else {
                ConnectionReport.stage(ConnectionReport.Stage.NO_SAVED_PROFILE);
                if(!NetworkState.validated(this)) throw new Exception("No saved connection settings for this profile. Use Wi-Fi once and tap Save connection settings before testing mobile data.");
                progress("Saving the connection profile for first use; Wi-Fi or mobile data is needed once");
            }
            JSONObject result = api.connect(profileId, this::progress);
            if (!"xray".equals(result.optString("engine"))) throw new Exception("Only imported connection profiles are supported. Ask your admin to replace this profile.");
            xrayLease=result.getString("lease"); hadLease=true;
            leaseDeadline=android.os.SystemClock.elapsedRealtime()+30000;
            synchronized(xrayLock) {
                if(!running.get()) return;
                if(xray!=null) { xray.stop(); xray=null; }
            }
            runXray(api, result);
        } catch (LinkageError error) {
            ConnectionReport.stage(ConnectionReport.Stage.ENGINE_LOAD_FAILED);
            if (running.get()) detail = "The Xray engine could not load on this phone. Install the complete current APK.";
        } catch (Exception error) {
            if (running.get()) {
                XrayEngine engine = xray;
                int proxyStatus=engine==null?0:engine.upstreamStatus();
                if(proxyStatus!=0){error=new ProxyFailure(proxyStatus);proxyFailure=true;}
                if(error instanceof Api.HttpError && ((Api.HttpError)error).status == 429)proxyFailure=true;
                retryFailure=RetryPolicy.transientFailure(error);
                ConnectionReport.failure(null, error);
                detail = error instanceof Api.HttpError ? CustomerMessage.forStatus(((Api.HttpError)error).status) : CustomerMessage.connection();
            }
        } finally {
            stopTunnel();
            if (xrayLease != null) try {
                JSONObject released = new Api(new Vault(this)).request("/v1/xray/disconnect", new JSONObject().put("lease", xrayLease), true);
                leaseReleased = released.optBoolean("ok");
            } catch (Exception ignored) {}
        }
    }
    private void runXray(Api api, JSONObject result) throws Exception {
        JSONObject profile = result.getJSONObject("profile");
        String lease = result.getString("lease"); xrayLease = lease;
        if (!running.get()) return;
        leaseDeadline = android.os.SystemClock.elapsedRealtime() + 30000;
        progress("Creating the Android VPN interface");
        ConnectionReport.stage(ConnectionReport.Stage.VPN_INTERFACE);
        // Native sockets bypass the TUN; API calls explicitly use its loopback control proxy.
        Builder builder = new Builder().setSession("Top private Plug")
            .setMtu(1400).addAddress("10.99.0.2", 30).addAddress("fd00:99::2", 126)
            .addRoute("0.0.0.0", 0).addRoute("::", 0).addDnsServer("1.1.1.1").setBlocking(false);
        builder.addDisallowedApplication(getPackageName());
        XrayEngine engine;
        synchronized (xrayLock) {
            if (!running.get()) return;
            tun = builder.establish();
            if (tun == null) throw new Exception("Android could not create the VPN interface.");
            engine = new XrayEngine(getFilesDir()); xray = engine;
            JSONObject config = TunnelConfig.control(result.getJSONObject("config"),new Vault(this).endpoint(),controlPort,false);
            // Android owns the TUN. Avoid desktop name discovery (net.Interfaces).
            config.getJSONArray("inbounds").getJSONObject(0).getJSONObject("settings").put("name", "tpp0");
            progress("Starting Xray with the imported VLESS or Trojan profile");
            ConnectionReport.stage(ConnectionReport.Stage.NATIVE_START);
            engine.start(config.toString(), tun.getFd());
            Api.throughTunnel(new Vault(this).endpoint(),controlPort,engine::clearUpstreamStatus);
        }
        progress("Checking HTTPS traffic through the Xray tunnel");
        ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_HTTPS);
        // Use the pinned core's HTTPS connectivity target. Admin-host reachability
        // is checked independently by authenticated API calls and heartbeats.
        latency = engine.probe("");
        if (latency < 0) throw new RetryPolicy.TransportFailure("The tunnel HTTPS check failed.");
        synchronized (this) {
            if (!running.get()) return;
            connectedAt=android.os.SystemClock.elapsedRealtime();
            state = "Connected";
            ConnectionReport.stage(ConnectionReport.Stage.CONNECTED);
            detail = profile.optBoolean("insecure_tls") ? "Test profile: server certificate verification is disabled." : "Your connection is active.";
            showNotification(detail);
        }
        TrafficTotals totals = new TrafficTotals();
        long nextHeartbeat = 0;
        while (running.get() && engine.running()) {
            synchronized (xrayLock) {
                if (!running.get()) break;
                totals.add(engine.traffic(), "trojan");
                uploaded = totals.up; downloaded = totals.down;
            }
            if (android.os.SystemClock.elapsedRealtime() < nextHeartbeat) {
                try { Thread.sleep(1000); } catch (InterruptedException cancelled) { break; }
                continue;
            }
            try {
                JSONObject check = api.request("/v1/xray/heartbeat", new JSONObject().put("lease", lease)
                    .put("up", uploaded).put("down", downloaded), true);
                if (!check.optBoolean("ok")) throw new Exception("Account check failed.");
                // Failed heartbeats never extend the account authorization deadline.
                leaseDeadline = android.os.SystemClock.elapsedRealtime() + 30000;
                nextHeartbeat = android.os.SystemClock.elapsedRealtime() + 5000;
                resetRetryAfterStableHeartbeat(android.os.SystemClock.elapsedRealtime());
            } catch (Exception error) {
                if (!running.get()) break;
                if (!RetryPolicy.transientFailure(error)) throw error;
                ConnectionReport.stage(ConnectionReport.Stage.HEARTBEAT_RETRY);
                // Keep an authorized tunnel alive only within its existing lease.
                try { Thread.sleep(1500); } catch (InterruptedException cancelled) { break; }
                continue;
            }
            try { Thread.sleep(1000); } catch (InterruptedException ignored) { break; }
        }
        if (running.get()) throw new RetryPolicy.TransportFailure("The Xray engine stopped unexpectedly.");
    }
    private void resetRetryAfterStableHeartbeat(long now) {
        if(retryAttempt > 0 && RetryPolicy.stable(connectedAt, now)) {
            retryAttempt = 0;
            ConnectionReport.stage(ConnectionReport.Stage.RECOVERY_STABLE);
        }
    }
    private void closeTransport() {
        Api.clearTunnel();
        try { if (tun != null) { tun.close(); tun = null; } } catch (Exception ignored) {}
        synchronized (xrayLock) {
            if (xray != null) { xray.stop(); xray = null; }
            try { if (tun != null) { tun.close(); tun = null; } } catch (Exception ignored) {}
        }
    }
    private synchronized void stopTunnel() {
        running.set(false);
        if (!stopping.compareAndSet(false, true)) return;
        state = "Disconnecting";
        ConnectionReport.stage(ConnectionReport.Stage.CANCEL_OR_CLEANUP);
        if (pinger != null) pinger.interrupt();
        if (worker != null) worker.interrupt();
        // Native startup holds xrayLock and stopLoop can wait on native I/O.
        // Lifecycle callbacks must never acquire that lock or call native shutdown.
        new Thread(() -> {
            try {
                closeTransport();
                Thread previous = worker;
                if (previous != null && previous != Thread.currentThread()) {
                    try { previous.join(); } catch (InterruptedException cancelled) { Thread.currentThread().interrupt(); }
                }
            }
            finally {
                main.post(() -> {
                    onCleanupComplete();
                });
            }
        }, "tpp-tunnel-cleanup").start();
    }
    @Override public void onRevoke() { ConnectionReport.stage(ConnectionReport.Stage.ANDROID_REVOKED); requestStop(); }
    @Override public void onDestroy() {
        if(connectivity != null && networkCallback != null) {
            try { connectivity.unregisterNetworkCallback(networkCallback); } catch(RuntimeException ignored) {}
        }
        requestStop(); super.onDestroy();
    }
}




