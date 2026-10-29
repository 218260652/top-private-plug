package za.co.topprivateplug;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import org.json.JSONArray;
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
    void endpoint(String value) { synchronized(Vault.class) { prefs.edit().putString("endpoint", value).remove("token").remove("catalog").remove("bootstrap").commit();
    } }
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
    private String encrypt(String value) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
        return Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" + Base64.encodeToString(cipher.doFinal(value.getBytes("UTF-8")), Base64.NO_WRAP);
    }
    private String decrypt(String value) throws Exception {
        if (value.isEmpty()) return "";
        String[] parts = value.split(":",2);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), "UTF-8");
    }
    void token(String value) throws Exception { synchronized(Vault.class) {
        SharedPreferences.Editor edit=prefs.edit().remove("catalog").remove("bootstrap");
        if(value.isEmpty()) edit.remove("token"); else edit.putString("token",encrypt(value));
        if(!edit.commit()) throw new Exception("Could not save access on this phone.");

    } }
    String token() { synchronized(Vault.class) {
        try { return decrypt(prefs.getString("token", "")); } catch(Exception error) { return ""; }

    } }
    private String scope() throws Exception {
        byte[] value=java.security.MessageDigest.getInstance("SHA-256").digest((endpoint()+"\n"+token()).getBytes("UTF-8"));
        return Base64.encodeToString(value,Base64.NO_WRAP);
    }
    void catalog(JSONArray profiles) throws Exception { synchronized(Vault.class) {
        if(token().isEmpty()) return;
        String value=new JSONObject().put("scope",scope()).put("profiles",profiles).toString();
        if(!prefs.edit().putString("catalog",encrypt(value)).commit()) throw new Exception("Could not save connection list.");

    } }
    JSONArray catalog() { synchronized(Vault.class) {
        try {
            if(token().isEmpty()) return new JSONArray();
            JSONObject value=new JSONObject(decrypt(prefs.getString("catalog","")));
            return scope().equals(value.optString("scope"))?value.getJSONArray("profiles"):new JSONArray();
        } catch(Exception ignored) { return new JSONArray(); }

    } }
    void bootstrap(String profileId, JSONObject result, String expectedToken, String expectedOrigin) throws Exception { synchronized(Vault.class) {
        if(!expectedToken.equals(token()) || !expectedOrigin.equals(endpoint())) throw new Exception("Saved access changed during connection. Retry.");
        if(token().isEmpty()) throw new Exception("Activate your access first.");
        JSONObject records;
        try { records=new JSONObject(decrypt(prefs.getString("bootstrap",""))); } catch(Exception ignored) { records=new JSONObject(); }
        if(!scope().equals(records.optString("scope"))) records=new JSONObject().put("scope",scope()).put("profiles",new JSONObject());
        // Leases are single-session credentials and are never cached or reused.
        JSONObject value=new JSONObject().put("config",result.getJSONObject("config"))
            .put("profile",result.getJSONObject("profile"));
        records.getJSONObject("profiles").put(profileId,value);
        if(!prefs.edit().putString("bootstrap",encrypt(records.toString())).commit()) throw new Exception("Could not save the connection profile.");

    } }
    JSONObject bootstrap(String profileId) { synchronized(Vault.class) {
        try {
            if(token().isEmpty()) return null;
            JSONObject value=new JSONObject(decrypt(prefs.getString("bootstrap","")));
            return scope().equals(value.optString("scope"))?value.getJSONObject("profiles").optJSONObject(profileId):null;
        } catch(Exception ignored) { return null; }

    } }
}
