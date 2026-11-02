package za.co.topprivateplug;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

final class DeviceKey {
    private static synchronized KeyStore store() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias("tpp_device")) {
            KeyPairGenerator generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
            generator.initialize(new KeyGenParameterSpec.Builder("tpp_device", KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1")).setDigests(KeyProperties.DIGEST_SHA256).build());
            generator.generateKeyPair();
        }
        return store;
    }
    static String publicKey() throws Exception { return Base64.encodeToString(store().getCertificate("tpp_device").getPublicKey().getEncoded(), Base64.NO_WRAP); }
    static String sign(String message) throws Exception {
        Signature signature = Signature.getInstance("SHA256withECDSA");
        signature.initSign((PrivateKey)store().getKey("tpp_device", null));
        signature.update(message.getBytes("UTF-8"));
        return Base64.encodeToString(signature.sign(), Base64.NO_WRAP);
    }
}

