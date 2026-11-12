package za.co.topprivateplug;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.provider.Settings;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InterruptedIOException;
import java.io.OutputStream;
import java.net.URL;
import java.security.MessageDigest;

import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

/** Downloads the customer build only from the signed-in account service. */
final class CustomerUpdate {
    private final Activity activity;
    private final Vault vault;
    private final CustomerApi api;

    CustomerUpdate(Activity activity, Vault vault, CustomerApi api) {
        this.activity = activity;
        this.vault = vault;
        this.api = api;
    }

    JSONObject check() throws Exception {
        JSONObject release = api.call("app-update", null);
        int installed = activity.getPackageManager().getPackageInfo(activity.getPackageName(), 0).versionCode;
        if (!release.optBoolean("available") || release.getInt("version_code") <= installed) return null;
        String name = release.getString("version_name");
        String hash = release.getString("sha256");
        long size = release.getLong("size");
        if (!name.matches("[A-Za-z0-9._+-]{1,60}") || !hash.matches("[0-9a-f]{64}")
                || size < 10000 || size > 100L * 1024 * 1024) {
            throw new IOException("The update information could not be verified.");
        }
        return release;
    }

    void download(JSONObject release) throws Exception {
        File apk = apk();
        File folder = apk.getParentFile();
        if (!folder.isDirectory() && !folder.mkdirs() && !folder.isDirectory()) {
            throw new IOException("Could not create the update folder.");
        }
        String hash = release.getString("sha256");
        long expectedSize = release.getLong("size");
        if (apk.isFile() && apk.length() == expectedSize) {
            try (InputStream in = new FileInputStream(apk)) {
                if (hash.equals(readHash(in, null, expectedSize))) {
                    UpdateController.verifyApk(activity, apk, release);
                    return;
                }
            }
        }
        File partial = File.createTempFile("download-", ".part", folder);
        HttpsURLConnection connection = null;
        try {
            URL url = new URL(Vault.STAGING_ORIGIN + "/v2/customer/app-update-apk?sha256=" + hash);
            connection = (HttpsURLConnection) url.openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(15000);
            connection.setReadTimeout(20000);
            connection.setRequestProperty("Authorization", "Bearer " + vault.customerSession().getString("access"));
            if (connection.getResponseCode() != 200) {
                throw new IOException("Update download unavailable. Check for updates again.");
            }
            try (InputStream in = connection.getInputStream(); OutputStream out = new FileOutputStream(partial)) {
                if (!hash.equals(readHash(in, out, expectedSize))) throw new IOException("Update checksum mismatch.");
            }
            UpdateController.verifyApk(activity, partial, release);
            if (!partial.renameTo(apk)) throw new IOException("Could not save the verified update.");
        } finally {
            if (connection != null) connection.disconnect();
            partial.delete();
        }
    }

    private static String readHash(InputStream in, OutputStream out, long expected) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[32768];
        long total = 0;
        for (int count; (count = in.read(buffer)) != -1;) {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException();
            total += count;
            if (total > expected) throw new IOException("Update size mismatch.");
            digest.update(buffer, 0, count);
            if (out != null) out.write(buffer, 0, count);
        }
        if (total != expected) throw new IOException("Update size mismatch.");
        return UpdateController.hex(digest.digest());
    }

    private File apk() {
        return new File(activity.getFilesDir(), "updates/pilot.apk");
    }

    void install() throws IOException {
        if (!activity.getPackageManager().canRequestPackageInstalls()) {
            activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + activity.getPackageName())));
            throw new IOException("Allow installs from Top Private Plug, then open App updates again.");
        }
        Uri apkUri = Uri.parse("content://" + activity.getPackageName() + ".updates/pilot.apk");
        Intent installer = new Intent(Intent.ACTION_INSTALL_PACKAGE)
            .setDataAndType(apkUri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        installer.setClipData(ClipData.newRawUri("Verified app update", apkUri));
        activity.startActivity(installer);
    }
}
