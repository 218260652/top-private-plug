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
    static final String DEFAULT_SERVICE_ORIGIN = "https://top-private-plug-test-api.onrender.com";
    private final SharedPreferences prefs;
    Vault(Context context) {
        prefs = context.getSharedPreferences("tpp", Context.MODE_PRIVATE);
        synchronized(Vault.class) {
            if(!prefs.contains("access_migrated")) {
                String legacyNetwork="MTN";
                try{JSONArray old=new JSONObject(decrypt(prefs.getString("catalog",""))).getJSONArray("profiles");java.util.Set<String> names=new java.util.HashSet<>();for(int i=0;i<old.length();i++){String n=old.getJSONObject(i).optString("carrier");if(java.util.Arrays.asList("MTN","Cell C","Telkom").contains(n))names.add(n);}if(names.size()==1)legacyNetwork=names.iterator().next();}catch(Exception ignored){}
                SharedPreferences.Editor edit=prefs.edit().putString("active_network",legacyNetwork);
                for(String name:new String[]{"token","catalog","bootstrap","history"}) {
                    if(prefs.contains(name))edit.putString("access."+legacyNetwork+"."+name,prefs.getString(name,""));
                    edit.remove(name);
                }
                if(!edit.putBoolean("access_migrated",true).commit())throw new IllegalStateException("Could not migrate saved access");
            }
        }
    }
    private String stored(String name){return "access."+network()+"."+name;}
    String network(){return prefs.getString("active_network","MTN");}
    void selectNetwork(String name){synchronized(Vault.class){
        if(!java.util.Arrays.asList("MTN","Cell C","Telkom").contains(name))throw new IllegalArgumentException("Unknown network");
        if(!prefs.edit().putString("active_network",name).commit())throw new IllegalStateException("Could not select access");
    }}
    boolean hasAnyAccess(){synchronized(Vault.class){for(String n:new String[]{"MTN","Cell C","Telkom"})if(!prefs.getString("access."+n+".token","").isEmpty())return true;return false;}}
    void saveAccount(JSONObject account)throws Exception{synchronized(Vault.class){if(!prefs.edit().putString(stored("account"),encrypt(account.toString())).commit())throw new Exception("Could not save account overview");}}
    JSONObject savedAccount(){synchronized(Vault.class){try{return new JSONObject(decrypt(prefs.getString(stored("account"),"")));}catch(Exception e){return null;}}}
    void activateToken(String value,JSONObject account)throws Exception{synchronized(Vault.class){
        String id=account.getString("id"), current=network();
        if(!account.optString("carrier",current).equals(current))throw new Exception("Activation network does not match this slot");
        // Reusing the same code rotates its server token. Update every saved
        // reference to that account, preserving each slot's scoped profile cache.
        String copyFrom=null;
        for(String n:new String[]{"MTN","Cell C","Telkom"})try{
            JSONObject a=new JSONObject(decrypt(prefs.getString("access."+n+".account","")));
            if(id.equals(a.optString("id"))){copyFrom=n;break;}
        }catch(Exception ignored){}
        SharedPreferences.Editor edit=prefs.edit();
        String newScope=scopeFor(value);
        for(String n:new String[]{"MTN","Cell C","Telkom"}){
            boolean same=false;try{same=id.equals(new JSONObject(decrypt(prefs.getString("access."+n+".account",""))).optString("id"));}catch(Exception ignored){}
            if(!n.equals(current)&&!same)continue;
            String source=n.equals(current)&&!same?copyFrom:n;
            edit.putString("access."+n+".token",encrypt(value)).putString("access."+n+".account",encrypt(account.toString()));
            for(String cache:new String[]{"catalog","bootstrap","history"}){
                edit.remove("access."+n+"."+cache);
                if(source!=null)try{
                    JSONObject cached=new JSONObject(decrypt(prefs.getString("access."+source+"."+cache,"")));
                    cached.put("scope",newScope);edit.putString("access."+n+"."+cache,encrypt(cached.toString()));
                }catch(Exception ignored){}
            }
        }
        if(!edit.commit())throw new Exception("Could not save access on this phone");
    }}
    private String scopeFor(String accessToken)throws Exception{
        return Base64.encodeToString(java.security.MessageDigest.getInstance("SHA-256").digest((endpoint()+"\n"+accessToken).getBytes("UTF-8")),Base64.NO_WRAP);
    }
    String endpoint() { return prefs.getString("endpoint", DEFAULT_SERVICE_ORIGIN); }
    void endpoint(String value) { synchronized(Vault.class) {
        SharedPreferences.Editor edit=prefs.edit().putString("endpoint",value);
        for(String n:new String[]{"MTN","Cell C","Telkom"})for(String k:new String[]{"token","account","catalog","bootstrap","history"})edit.remove("access."+n+"."+k);
        if(!edit.commit())throw new IllegalStateException("Could not change service");
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
        SharedPreferences.Editor edit=prefs.edit().remove(stored("account")).remove(stored("catalog")).remove(stored("bootstrap")).remove(stored("history"));
        if(value.isEmpty()) edit.remove(stored("token")); else edit.putString(stored("token"),encrypt(value));
        if(!edit.commit()) throw new Exception("Could not save access on this phone.");

    } }
    String token() { synchronized(Vault.class) {
        try { return decrypt(prefs.getString(stored("token"), "")); } catch(Exception error) { return ""; }

    } }
    private String scope() throws Exception {
        byte[] value=java.security.MessageDigest.getInstance("SHA-256").digest((endpoint()+"\n"+token()).getBytes("UTF-8"));
        return Base64.encodeToString(value,Base64.NO_WRAP);
    }
    void catalog(JSONArray profiles) throws Exception { synchronized(Vault.class) {
        if(token().isEmpty()) return;
        String value=new JSONObject().put("scope",scope()).put("profiles",profiles).toString();
        if(!prefs.edit().putString(stored("catalog"),encrypt(value)).commit()) throw new Exception("Could not save connection list.");

    } }
    JSONArray catalog() { synchronized(Vault.class) {
        try {
            if(token().isEmpty()) return new JSONArray();
            JSONObject value=new JSONObject(decrypt(prefs.getString(stored("catalog"),"")));
            return scope().equals(value.optString("scope"))?value.getJSONArray("profiles"):new JSONArray();
        } catch(Exception ignored) { return new JSONArray(); }

    } }
    void bootstrap(String profileId, JSONObject result, String expectedToken, String expectedOrigin) throws Exception { synchronized(Vault.class) {
        if(!expectedToken.equals(token()) || !expectedOrigin.equals(endpoint())) throw new Exception("Saved access changed during connection. Retry.");
        if(token().isEmpty()) throw new Exception("Activate your access first.");
        JSONObject records;
        try { records=new JSONObject(decrypt(prefs.getString(stored("bootstrap"),""))); } catch(Exception ignored) { records=new JSONObject(); }
        if(!scope().equals(records.optString("scope"))) records=new JSONObject().put("scope",scope()).put("profiles",new JSONObject());
        // Leases are single-session credentials and are never cached or reused.
        JSONObject value=new JSONObject().put("config",result.getJSONObject("config"))
            .put("profile",result.getJSONObject("profile"));
        records.getJSONObject("profiles").put(profileId,value);
        if(!prefs.edit().putString(stored("bootstrap"),encrypt(records.toString())).commit()) throw new Exception("Could not save the connection profile.");

    } }
    JSONObject bootstrap(String profileId) { synchronized(Vault.class) {
        try {
            if(token().isEmpty()) return null;
            JSONObject value=new JSONObject(decrypt(prefs.getString(stored("bootstrap"),"")));
            return scope().equals(value.optString("scope"))?value.getJSONObject("profiles").optJSONObject(profileId):null;
        } catch(Exception ignored) { return null; }

    } }
    JSONArray mergeHistory(JSONArray fresh,int hours,String expectedToken,String expectedOrigin) throws Exception { synchronized(Vault.class) {
        if(!expectedToken.equals(token())||!expectedOrigin.equals(endpoint()))throw new Exception("Account changed during history refresh.");
        if(token().isEmpty())return new JSONArray();
        java.util.TreeMap<Long,JSONObject> records=new java.util.TreeMap<>();
        try {JSONObject stored=new JSONObject(decrypt(prefs.getString(stored("history"),"")));if(scope().equals(stored.optString("scope"))){JSONArray items=stored.getJSONArray("points");for(int i=0;i<items.length();i++){JSONObject v=items.getJSONObject(i);records.put(v.getLong("at"),v);}}}catch(Exception ignored){}
        for(int i=0;i<fresh.length();i++){JSONObject v=fresh.getJSONObject(i);records.put(v.getLong("at"),v);}
        long now=System.currentTimeMillis()/1000;records.headMap(now-7*86400L).clear();
        while(records.size()>10080)records.pollFirstEntry();
        JSONArray all=new JSONArray(),selected=new JSONArray();for(java.util.Map.Entry<Long,JSONObject> entry:records.entrySet()){all.put(entry.getValue());if(entry.getKey()>=now-hours*3600L)selected.put(entry.getValue());}
        prefs.edit().putString(stored("history"),encrypt(new JSONObject().put("scope",scope()).put("points",all).toString())).apply();return selected;
    } }
}

