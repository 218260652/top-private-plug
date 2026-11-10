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
    static final String TUNNEL_RUNNING = "Tunnel running";
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
    private volatile boolean reconnectAllowed, retryFailure, proxyFailure, retryPending, hadLease;
    private int retryAttempt;
    private String activeProfile, accessToken, accountOrigin;
    private Runnable retryTask;

    private String sessionMarker(Vault vault) {
        return vault.staging ? vault.customerSession().optString("marker") : vault.token();
    }

    private void requestStop() {
        reconnectAllowed = false;
        retryPending = false;
        if (retryTask != null) main.removeCallbacks(retryTask);
        if (!"Disconnected".equals(state)) detail = "Closing the VPN connection…";
        stopTunnel();
    }

    private void beginAttempt() {
        if (!reconnectAllowed || VpnService.prepare(this) != null) { requestStop(); return; }
        running.set(true);
        retryFailure = proxyFailure = hadLease = false;
        state = retryAttempt == 0 ? "Connecting" : "Reconnecting";
        detail = retryAttempt == 0 ? "Starting VPN service…" : "Reconnecting (attempt " + retryAttempt + "/5)…";
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
            && accessToken.equals(sessionMarker(vault)) && accountOrigin.equals(vault.endpoint());
        if (reconnectAllowed && retryFailure && sameAccess && retryAttempt < RetryPolicy.MAX_RETRIES) {
            retryAttempt++;
            long delay = RetryPolicy.delayMillis(retryAttempt, proxyFailure, hadLease);
            state = "Reconnecting";
            detail = detail + "\nRetrying (" + retryAttempt + "/5). Tap Cancel to stop.";
            retryPending = true;
            ConnectionReport.stage(ConnectionReport.Stage.RECONNECT_SCHEDULED);
            showNotification(detail);
            retryTask = () -> {
                retryPending = false;
                Vault current = new Vault(this);
                if (!reconnectAllowed || !accessToken.equals(sessionMarker(current)) || !accountOrigin.equals(current.endpoint())) {
                    requestStop(); return;
                }
                beginAttempt();
            };
            main.postDelayed(retryTask, delay);
            return;
        }
        if (reconnectAllowed && retryFailure && retryAttempt >= RetryPolicy.MAX_RETRIES) {
            detail = detail + "\nRetry limit reached. Open Connection report for details.";
            ConnectionReport.stage(ConnectionReport.Stage.RECONNECT_EXHAUSTED);
        }
        reconnectAllowed = false;
        stopping.set(true);
        if (foreground) { stopForeground(STOP_FOREGROUND_REMOVE); foreground = false; }
        state = "Disconnected";
        if ("Closing the VPN connection…".equals(detail)) detail = "";
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
        accessToken = sessionMarker(vault); accountOrigin = vault.endpoint();
        retryAttempt = 0; reconnectAllowed = true;
        beginAttempt();
        return START_NOT_STICKY;
    }
    private void showNotification(String text) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("vpn", "VPN connection", NotificationManager.IMPORTANCE_LOW));
        Class<?> launcher = new Vault(this).staging ? CustomerActivity.class : MainActivity.class;
        PendingIntent activity = PendingIntent.getActivity(this, 0, new Intent(this, launcher), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
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
            if (vault.staging) {
                JSONObject config = vault.customerTunnelProfile(profileId);
                if (config == null || accessToken.isEmpty() || !accessToken.equals(sessionMarker(vault))) {
                    ConnectionReport.stage(ConnectionReport.Stage.NO_SAVED_PROFILE);
                    throw new Exception("Use working internet to save this profile first.");
                }
                ConnectionReport.stage(ConnectionReport.Stage.SAVED_PROFILE_START);
                runXray(config, null, null);
            } else {
                JSONObject result = api.connect(profileId, this::progress);
                if (!"xray".equals(result.optString("engine"))) throw new Exception("Only imported connection profiles are supported. Ask your admin to replace this profile.");
                xrayLease = result.getString("lease");
                hadLease = true;
                leaseDeadline = android.os.SystemClock.elapsedRealtime() + leaseMillis(result);
                runXray(result.getJSONObject("config"), result.getJSONObject("profile"), api);
            }
        } catch (LinkageError error) {
            ConnectionReport.stage(ConnectionReport.Stage.ENGINE_LOAD_FAILED);
            if (running.get()) detail = "The Xray engine could not load on this phone. Install the complete current APK.";
        } catch (Exception error) {
            if (running.get()) {
                XrayEngine engine = xray;
                int proxyStatus=engine==null?0:engine.upstreamStatus();
                if (proxyStatus != 0 && !(error instanceof Api.HttpError)) {
                    error = new ProxyFailure(proxyStatus);
                }
                proxyFailure |= error instanceof ProxyFailure;
                retryFailure=RetryPolicy.transientFailure(error);
                ConnectionReport.failure(null, error);
                detail = error instanceof Api.HttpError
                    ? (new Vault(this).staging ? error.getMessage() : CustomerMessage.forStatus(((Api.HttpError)error).status))
                    : connectionFailure(error);
            }
        } finally {
            stopTunnel();
            if (xrayLease != null) try {
                new Api(new Vault(this)).request("/v1/xray/disconnect", new JSONObject().put("lease", xrayLease), true);
            } catch (Exception ignored) {}
        }
    }
    private String connectionFailure(Exception error) {
        if (error instanceof ProxyFailure) return "The upstream proxy returned HTTP " + ((ProxyFailure) error).status + ".";
        if (error instanceof RetryPolicy.TransportFailure && "Checking HTTPS traffic through the Xray tunnel".equals(phase))
            return "VPN started, but no HTTPS traffic passed the tunnel check.";
        String category = ConnectionReport.category(error);
        return "OTHER_ERROR".equals(category) ? CustomerMessage.connection() : "Connection failed: " + category.replace('_', ' ').toLowerCase(java.util.Locale.ROOT) + ".";
    }

    private static long httpsProbe(XrayEngine engine, String url) throws Exception {
        long delay = engine.probe(url);
        if (delay < 0) throw new RetryPolicy.TransportFailure("The tunnel HTTPS check failed.");
        return delay;
    }

    private void runXray(JSONObject source, JSONObject profile, Api api) throws Exception {
        if (!running.get()) return;
        JSONObject config = api == null ? new JSONObject(source.toString())
            : TunnelConfig.control(source, new Vault(this).endpoint(), controlPort, false);
        boolean staging = api == null;
        boolean unverifiedTls = staging && Vault.usesBundledProfile(activeProfile)
            && config.getJSONArray("outbounds").getJSONObject(0).getJSONObject("streamSettings")
                .getJSONObject("tlsSettings").optBoolean("allowInsecure");
        if (staging) {
            TunnelConfig.useCloudflareHttpsDns(config);
            boolean proxied = TunnelConfig.hasHttpUpstream(config);
            ConnectionReport.stage(proxied ? ConnectionReport.Stage.HTTP_UPSTREAM_ROUTE
                : ConnectionReport.Stage.DIRECT_ENDPOINT_ROUTE);
            if (!proxied) TunnelConfig.resolveDirectEndpoint(config, this);
        }
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
            // Android owns the TUN. Avoid desktop name discovery (net.Interfaces).
            config.getJSONArray("inbounds").getJSONObject(0).getJSONObject("settings").put("name", "tpp0");
            progress("Starting Xray with the imported VLESS or Trojan profile");
            ConnectionReport.stage(ConnectionReport.Stage.NATIVE_START);
            engine.start(config.toString(), tun.getFd());
            if (api != null) Api.throughTunnel(new Vault(this).endpoint(), controlPort, engine::clearUpstreamStatus);
        }
        if (!staging) {
            progress("Checking HTTPS traffic through the Xray tunnel");
            ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_HTTPS);
            try {
                latency = httpsProbe(engine, "");
            } catch (Exception error) {
                ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_HTTPS_FAILED);
                throw error;
            }
            ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_HTTPS_OK);
        }
        if (!engine.running()) throw new RetryPolicy.TransportFailure("The Xray engine stopped unexpectedly.");
        synchronized (this) {
            if (!running.get()) return;
            if (api == null) leaseDeadline = Long.MAX_VALUE;
            connectedAt=android.os.SystemClock.elapsedRealtime();
            if (staging) {
                state = TUNNEL_RUNNING;
                ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_STARTED_UNVERIFIED);
                detail = unverifiedTls ? "Test profile: VLESS server certificate verification is disabled."
                    : "VPN interface is active. Internet access has not been verified.";
            } else {
                state = "Connected";
                ConnectionReport.stage(ConnectionReport.Stage.CONNECTED);
                detail = profile != null && profile.optBoolean("insecure_tls") ? "Test profile: server certificate verification is disabled." : "Your connection is active.";
            }
            showNotification(detail);
        }
        if (staging) verifyStagingTraffic(engine, unverifiedTls);
        TrafficTotals totals = new TrafficTotals();
        long nextHeartbeat = 0;
        while (running.get() && engine.running()) {
            synchronized (xrayLock) {
                if (!running.get()) break;
                totals.add(engine.traffic(), "trojan");
                uploaded = totals.up; downloaded = totals.down;
            }
            if (api == null || android.os.SystemClock.elapsedRealtime() < nextHeartbeat) {
                try { Thread.sleep(1000); } catch (InterruptedException cancelled) { break; }
                continue;
            }
            try {
                JSONObject usage = new JSONObject().put("lease", xrayLease).put("up", uploaded).put("down", downloaded);
                JSONObject check = api.request("/v1/xray/heartbeat", usage, true);
                if (!check.optBoolean("ok")) throw new Exception("Account check failed.");
                // Failed heartbeats never extend the account authorization deadline.
                leaseDeadline = android.os.SystemClock.elapsedRealtime() + leaseMillis(check);
                nextHeartbeat = android.os.SystemClock.elapsedRealtime() + 5000;
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
    private void verifyStagingTraffic(XrayEngine engine, boolean unverifiedTls) {
        if (!running.get()) return;
        ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_HTTPS);
        try {
            long delay = httpsProbe(engine, "");
            synchronized (this) {
                if (!running.get()) return;
                latency = delay;
                state = "Connected";
                detail = unverifiedTls ? "Traffic verified. Test profile skips VLESS server certificate verification."
                    : "Internet traffic verified through the VPN.";
                ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_HTTPS_OK);
                ConnectionReport.stage(ConnectionReport.Stage.CONNECTED);
                showNotification(detail);
            }
        } catch (Exception error) {
            if (!running.get()) return;
            ConnectionReport.trafficProbeFailed(false, error);
            engine.resetProbeDiagnostics();
            ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_IP_HTTPS);
            String result;
            try {
                httpsProbe(engine, "https://1.1.1.1/cdn-cgi/trace");
                if (!running.get()) return;
                ConnectionReport.stage(ConnectionReport.Stage.TUNNEL_IP_HTTPS_OK);
                result = "The VPN reached a test IP, but the website check failed.";
            } catch (Exception probeError) {
                if (!running.get()) return;
                ConnectionReport.trafficProbeFailed(true, probeError);
                result = "The VPN started, but the traffic checks failed. See Connection report.";
            }
            synchronized (this) {
                if (!running.get()) return;
                detail = unverifiedTls ? result + " Test profile skips VLESS server certificate verification." : result;
                showNotification(detail);
            }
        }
    }

    private long leaseMillis(JSONObject response) {
        return Math.max(0, Math.min(30, response.optInt("lease_seconds", 30))) * 1000L;
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
        if (worker != null && worker != Thread.currentThread()) worker.interrupt();
        // Native startup holds xrayLock and stopLoop can wait on native I/O.
        // Lifecycle callbacks must never acquire that lock or call native shutdown.
        Thread previous = worker;
        if (previous != null && previous != Thread.currentThread()) {
            // Closing the HTTPS request must not block the Android main thread or TUN teardown.
            new Thread(() -> Api.cancelRequest(previous), "tpp-account-cancel").start();
        }
        new Thread(() -> {
            try {
                closeTransport();
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
    @Override public void onRevoke() { requestStop(); }
    @Override public void onDestroy() { requestStop(); super.onDestroy(); }
}




