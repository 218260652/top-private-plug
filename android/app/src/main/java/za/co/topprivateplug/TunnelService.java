package za.co.topprivateplug;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.net.VpnService;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONObject;

public final class TunnelService extends VpnService {
    public static volatile String state = "Disconnected";
    public static volatile String detail = "";
    public static volatile long uploaded, downloaded, latency = -1;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private volatile ParcelFileDescriptor tun;
    private Thread worker, pinger;
    private boolean foreground;
    private volatile XrayEngine xray;
    private final Object xrayLock = new Object();
    private volatile long leaseDeadline;
    private String xrayLease;
    private volatile String phase = "Starting VPN service";

    private void progress(String message) throws Exception {
        if (!running.get()) throw new Exception("Connection cancelled.");
        phase = message;
        detail = message + "…";
        showNotification(detail);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) { stopTunnel(); stopSelf(); return START_NOT_STICKY; }
        if (intent == null) { stopSelf(startId); return START_NOT_STICKY; }
        if ((worker != null && worker.isAlive()) || !running.compareAndSet(false, true)) return START_NOT_STICKY;
        if (VpnService.prepare(this) != null) { running.set(false); stopSelf(); return START_NOT_STICKY; }
        showNotification("Connecting securely…");
        final String profileId = intent.getStringExtra("profile_id");
        worker = new Thread(() -> runTunnel(profileId), "tpp-tunnel"); worker.start();
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
        state = "Connecting"; detail = "Starting VPN service…"; uploaded = downloaded = 0; latency = -1;
        phase = "Starting VPN service";
        xrayLease = null;
        leaseDeadline = android.os.SystemClock.elapsedRealtime() + 75000;
        pinger = new Thread(() -> {
            while (running.get()) {
                if (android.os.SystemClock.elapsedRealtime() >= leaseDeadline) {
                    detail = "Connecting".equals(state)
                        ? "Timed out: " + phase + ". Share this startup stage with support."
                        : "Account check timed out. Reconnect when the service is reachable.";
                    // Publish failure before cleanup, including if native startup is blocked.
                    state = "Disconnected";
                    stopTunnel(); stopSelf(); return;
                }
                try { Thread.sleep(500); } catch (InterruptedException ignored) { return; }
            }
        }, "tpp-xray-watchdog"); pinger.start();
        try {
            if (profileId == null) throw new Exception("Choose a connection profile.");
            Api api = new Api(new Vault(this)); JSONObject result = api.connect(profileId, this::progress);
            if (!"xray".equals(result.optString("engine"))) throw new Exception("Only imported connection profiles are supported. Ask your admin to replace this profile.");
            runXray(api, result);
        } catch (LinkageError error) {
            detail = "The Xray engine could not load on this phone. Install the complete current APK.";
        } catch (Exception error) {
            if (running.get()) {
                String reason = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
                reason = reason.replaceAll("(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "[redacted UUID]");
                detail = "Failed: " + phase + ". " + reason;
                XrayEngine engine = xray;
                if (engine != null && !engine.diagnostic().isEmpty()) detail += "\nEngine: " + engine.diagnostic();
            }
        } finally {
            stopTunnel(); stopSelf();
            if (xrayLease != null) try { new Api(new Vault(this)).request("/v1/xray/disconnect", new JSONObject().put("lease", xrayLease), true); } catch (Exception ignored) {}
        }
    }
    private void runXray(Api api, JSONObject result) throws Exception {
        JSONObject profile = result.getJSONObject("profile");
        if (!running.get()) return;
        String lease = result.getString("lease"); xrayLease = lease;
        leaseDeadline = android.os.SystemClock.elapsedRealtime() + 30000;
        progress("Creating the Android VPN interface");
        // The app UID bypasses the TUN, preventing loops for both native sockets and API calls.
        Builder builder = new Builder().setSession("Top private Plug · " + profile.getString("name"))
            .setMtu(1400).addAddress("10.99.0.2", 30).addAddress("fd00:99::2", 126)
            .addRoute("0.0.0.0", 0).addRoute("::", 0).addDnsServer("1.1.1.1").setBlocking(false);
        builder.addDisallowedApplication(getPackageName());
        XrayEngine engine;
        synchronized (xrayLock) {
            if (!running.get()) return;
            tun = builder.establish();
            if (tun == null) throw new Exception("Android could not create the VPN interface.");
            engine = new XrayEngine(getFilesDir()); xray = engine;
            JSONObject config = result.getJSONObject("config");
            // Android owns the TUN. Avoid desktop name discovery (net.Interfaces).
            config.getJSONArray("inbounds").getJSONObject(0).getJSONObject("settings").put("name", "tpp0");
            progress("Starting Xray with the imported VLESS or Trojan profile");
            engine.start(config.toString(), tun.getFd());
        }
        progress("Checking HTTPS traffic through the Xray tunnel");
        latency = engine.probe(new Vault(this).endpoint() + "/health");
        if (!running.get()) return;
        state = "Connected";
        detail = profile.optBoolean("insecure_tls") ? "Test profile: server certificate verification is disabled." : "Xray / TLS · traffic check passed";
        showNotification(detail);
        while (running.get() && engine.running()) {
            synchronized (xrayLock) {
                if (!running.get()) break;
                for (String item : engine.traffic().split(";")) {
                    String[] values = item.split(",");
                    if (values.length != 3 || !"trojan".equals(values[0])) continue;
                    long count = Long.parseLong(values[2]);
                    if (count < 0) throw new Exception("Invalid traffic counter.");
                    if ("uplink".equals(values[1])) uploaded += count;
                    else if ("downlink".equals(values[1])) downloaded += count;
                }
            }
            JSONObject check = api.request("/v1/xray/heartbeat", new JSONObject().put("lease", lease)
                .put("up", uploaded).put("down", downloaded), true);
            if (!check.optBoolean("ok")) throw new Exception("Account check failed.");
            leaseDeadline = android.os.SystemClock.elapsedRealtime() + 30000;
            try { Thread.sleep(5000); } catch (InterruptedException ignored) { break; }
        }
    }
    private void closeTransport() {
        synchronized (xrayLock) {
            if (xray != null) { xray.stop(); xray = null; }
        }
        try { if (tun != null) { tun.close(); tun = null; } } catch (Exception ignored) {}
    }
    private void stopTunnel() {
        running.set(false); closeTransport();
        if (pinger != null) pinger.interrupt();
        state = "Disconnected";
        if (foreground) { stopForeground(STOP_FOREGROUND_REMOVE); foreground = false; }
    }
    @Override public void onRevoke() { stopTunnel(); stopSelf(); }
    @Override public void onDestroy() { stopTunnel(); super.onDestroy(); }
}



