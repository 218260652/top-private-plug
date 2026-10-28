package za.co.topprivateplug;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.net.VpnService;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.SNIHostName;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import org.json.JSONObject;

public final class TunnelService extends VpnService {
    public static volatile String state = "Disconnected";
    public static volatile String detail = "";
    public static volatile long uploaded, downloaded, latency = -1;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private volatile Socket raw;
    private volatile SSLSocket tls;
    private volatile ParcelFileDescriptor tun;
    private Thread worker, upload, pinger;
    private final Object writeLock = new Object();
    private DataOutputStream output;
    private FileInputStream packetInput;
    private FileOutputStream packetOutput;
    private boolean foreground;
    private volatile XrayEngine xray;
    private final Object xrayLock = new Object();
    private volatile long leaseDeadline;

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
    private void frame(byte[] bytes) throws Exception {
        synchronized (writeLock) { output.writeInt(bytes.length); output.write(bytes); output.flush(); }
    }
    private byte[] receive(DataInputStream input, int max) throws Exception {
        int size = input.readInt(); if (size < 1 || size > max) throw new Exception("Invalid gateway frame.");
        byte[] bytes = new byte[size]; input.readFully(bytes); return bytes;
    }
    private void runTunnel(String profileId) {
        state = "Connecting"; detail = ""; uploaded = downloaded = 0; latency = -1;
        try {
            if (profileId == null) throw new Exception("Choose a connection profile.");
            Api api = new Api(new Vault(this)); JSONObject result = api.connect(profileId);
            if ("xray".equals(result.optString("engine"))) { runXray(api, result); return; }
            JSONObject profile = result.getJSONObject("profile"); String sni = profile.getString("sni"); int port = profile.getInt("port");
            if (!running.get()) return;
            Socket socket = new Socket(); raw = socket;
            socket.bind(new InetSocketAddress(0));
            if (!protect(socket)) throw new Exception("Android could not protect the VPN socket.");
            socket.connect(new InetSocketAddress(profile.getString("server"), port), 12000); socket.setTcpNoDelay(true);
            SSLSocket secure = (SSLSocket)((SSLSocketFactory)SSLSocketFactory.getDefault()).createSocket(socket, sni, port, true); tls = secure;
            SSLParameters parameters = secure.getSSLParameters(); parameters.setEndpointIdentificationAlgorithm("HTTPS");
            parameters.setServerNames(Collections.singletonList(new SNIHostName(sni))); secure.setSSLParameters(parameters);
            boolean tls13 = Arrays.asList(secure.getSupportedProtocols()).contains("TLSv1.3");
            if ("1.3".equals(profile.getString("tls_min"))) {
                if (!tls13) throw new Exception("This profile requires TLS 1.3, which is unavailable on this phone.");
                secure.setEnabledProtocols(new String[]{"TLSv1.3"});
            } else secure.setEnabledProtocols(tls13 ? new String[]{"TLSv1.3", "TLSv1.2"} : new String[]{"TLSv1.2"});
            secure.setSoTimeout(20000); secure.startHandshake();
            output = new DataOutputStream(secure.getOutputStream()); DataInputStream input = new DataInputStream(secure.getInputStream());
            frame(new JSONObject().put("protocol", "TPP/1").put("ticket", result.getString("ticket")).toString().getBytes("UTF-8"));
            JSONObject hello = new JSONObject(new String(receive(input, 8192), "UTF-8"));
            if (!hello.optBoolean("ok")) throw new Exception(hello.optString("error", "Gateway rejected the connection."));
            if (!"TPP/1".equals(hello.getString("protocol")) || hello.getInt("mtu") != 1400) throw new Exception("Unsupported gateway settings.");
            Builder builder = new Builder().setSession("Top private Plug").setMtu(1400).setBlocking(true)
                .addAddress(hello.getString("address"), 30).addRoute("0.0.0.0", 0).addDnsServer(hello.getString("dns"))
                .addAddress("fd77:7470:7000::2", 128).addRoute("::", 0);
            // IPv6 is captured and dropped in this IPv4 pilot, never sent outside the VPN.
            ParcelFileDescriptor descriptor = builder.establish(); tun = descriptor;
            if (descriptor == null || !running.get()) throw new Exception("VPN permission was revoked.");
            packetInput = new ParcelFileDescriptor.AutoCloseInputStream(ParcelFileDescriptor.dup(descriptor.getFileDescriptor()));
            packetOutput = new ParcelFileDescriptor.AutoCloseOutputStream(ParcelFileDescriptor.dup(descriptor.getFileDescriptor()));
            secure.setSoTimeout(35000); state = "Connected"; showNotification("Connected · " + profile.getString("carrier"));
            upload = new Thread(() -> {
                try {
                    byte[] buffer = new byte[1401]; int size;
                    while (running.get() && (size = packetInput.read(buffer, 1, 1400)) > 0) {
                        if ((buffer[1] >> 4 & 15) != 4) continue;
                        buffer[0] = 1; frame(Arrays.copyOf(buffer, size + 1)); uploaded += size;
                    }
                } catch (Exception error) { if (running.get()) detail = "Tunnel transport stopped."; }
                finally { closeTransport(); }
            }, "tpp-upload"); upload.start();
            pinger = new Thread(() -> {
                try {
                    while (running.get()) {
                        byte[] ping = new byte[9]; ping[0] = 2;
                        long now = android.os.SystemClock.elapsedRealtime(); for (int i=8;i>0;i--) { ping[i] = (byte)now; now >>>= 8; }
                        frame(ping); Thread.sleep(10000);
                    }
                } catch (Exception ignored) { if (running.get()) closeTransport(); }
            }, "tpp-heartbeat"); pinger.start();
            while (running.get()) {
                byte[] bytes = receive(input, 1401);
                if (bytes[0] == 1 && bytes.length > 20) { packetOutput.write(bytes,1,bytes.length-1); downloaded += bytes.length-1; }
                else if (bytes[0] == 3 && bytes.length == 9) { long sent=0; for(int i=1;i<9;i++) sent=(sent<<8)|(bytes[i]&255L); latency=Math.max(0,android.os.SystemClock.elapsedRealtime()-sent); }
                else if (bytes[0] == 4) throw new Exception(new String(bytes,1,bytes.length-1,"UTF-8"));
                else throw new Exception("Invalid gateway packet.");
            }
        } catch (Exception error) {
            if (running.get()) detail = error.getMessage() == null ? "Connection failed." : error.getMessage();
        } finally {
            stopTunnel(); stopSelf();
            try { new Api(new Vault(this)).request("/v1/disconnect", new JSONObject(), true); } catch (Exception ignored) {}
        }
    }
    private void runXray(Api api, JSONObject result) throws Exception {
        JSONObject profile = result.getJSONObject("profile");
        if (!running.get()) return;
        String lease = result.getString("lease");
        leaseDeadline = android.os.SystemClock.elapsedRealtime() + 30000;
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
            engine.start(result.getJSONObject("config").toString(), tun.getFd());
        }
        pinger = new Thread(() -> {
            while (running.get()) {
                if (android.os.SystemClock.elapsedRealtime() >= leaseDeadline) {
                    detail = "Account check timed out. Reconnect when the service is reachable.";
                    stopTunnel(); stopSelf(); return;
                }
                try { Thread.sleep(500); } catch (InterruptedException ignored) { return; }
            }
        }, "tpp-xray-watchdog"); pinger.start();
        latency = engine.probe(new Vault(this).endpoint() + "/health");
        if (!running.get()) return;
        state = "Connected";
        detail = profile.optBoolean("insecure_tls") ? "Test profile: server certificate verification is disabled." : "Trojan / TLS · traffic check passed";
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
        try { if (raw != null) raw.close(); } catch (Exception ignored) {}
        try { if (tls != null) tls.close(); } catch (Exception ignored) {}
        try { if (packetInput != null) packetInput.close(); } catch (Exception ignored) {}
        try { if (packetOutput != null) packetOutput.close(); } catch (Exception ignored) {}
        try { if (tun != null) tun.close(); } catch (Exception ignored) {}
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

