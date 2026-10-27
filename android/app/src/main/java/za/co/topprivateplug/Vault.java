package za.co.topprivateplug;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class Vault {
    static final String DEFAULT_SERVICE_ORIGIN = "https://top-private-plug-admin.onrender.com";
    private final SharedPreferences prefs;
    Vault(Context context) { prefs = context.getSharedPreferences("tpp", Context.MODE_PRIVATE); }
    String endpoint() { return prefs.getString("endpoint", DEFAULT_SERVICE_ORIGIN); }
    void endpoint(String value) { prefs.edit().putString("endpoint", value).remove("token").apply(); }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias("tpp_storage")) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder("tpp_storage", KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey)store.getKey("tpp_storage", null);
    }
    synchronized void token(String value) throws Exception {
        if (value.isEmpty()) { prefs.edit().remove("token").apply(); return; }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
        String encrypted = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" + Base64.encodeToString(cipher.doFinal(value.getBytes("UTF-8")), Base64.NO_WRAP);
        prefs.edit().putString("token", encrypted).commit();
    }
    synchronized String token() {
        try {
            String value = prefs.getString("token", ""); if (value.isEmpty()) return "";
            String[] parts = value.split(":",2);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
            return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), "UTF-8");
        } catch (Exception error) { return ""; }
    }
}
