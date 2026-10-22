package com.autoquestion.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Private preferences contain ciphertext; the AES key never leaves Android Keystore. */
final class SecureStore {
    private static final String ALIAS = "autoquestion.api-key.v1";
    private final SharedPreferences preferences;

    SecureStore(Context context) {
        preferences = context.getSharedPreferences("settings", Context.MODE_PRIVATE);
    }

    ApiConfig config() {
        return new ApiConfig(preferences.getString("base_url", "https://api.deepseek.com"),
                preferences.getString("model", "deepseek-flash"));
    }

    boolean hasKey() { return preferences.contains("ciphertext"); }

    void save(ApiConfig config, String suppliedKey) throws Exception {
        SharedPreferences.Editor editor = preferences.edit();
        if (!suppliedKey.isEmpty()) {
            ApiConfig.validateKey(suppliedKey);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, encryptionKey());
            cipher.updateAAD(config.origin().getBytes(StandardCharsets.UTF_8));
            byte[] plaintext = suppliedKey.getBytes(StandardCharsets.UTF_8);
            try {
                editor.putString("ciphertext", Base64.encodeToString(cipher.doFinal(plaintext), Base64.NO_WRAP));
                editor.putString("iv", Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP));
                editor.putString("key_origin", config.origin());
            } finally { Arrays.fill(plaintext, (byte) 0); }
        } else if (!hasKey()) {
            throw new IllegalArgumentException("第一次使用请填写 API Key。");
        } else if (!config.origin().equals(preferences.getString("key_origin", ""))) {
            throw new IllegalArgumentException("API 地址已更换到其他服务器，请重新填写该服务器的 API Key。");
        }
        editor.putString("base_url", config.baseUrl).putString("model", config.model);
        if (!editor.commit()) throw new Exception("保存失败");
    }

    String readKey(ApiConfig config) throws Exception {
        if (!config.origin().equals(preferences.getString("key_origin", ""))) {
            throw new Exception("API Key 与服务器不匹配");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        byte[] iv = Base64.decode(preferences.getString("iv", ""), Base64.NO_WRAP);
        cipher.init(Cipher.DECRYPT_MODE, encryptionKey(), new GCMParameterSpec(128, iv));
        cipher.updateAAD(config.origin().getBytes(StandardCharsets.UTF_8));
        byte[] plaintext = cipher.doFinal(Base64.decode(preferences.getString("ciphertext", ""), Base64.NO_WRAP));
        try { return new String(plaintext, StandardCharsets.UTF_8); }
        finally { Arrays.fill(plaintext, (byte) 0); }
    }

    void forget() throws Exception {
        if (!preferences.edit().remove("ciphertext").remove("iv").remove("key_origin").commit()) {
            throw new Exception("清除失败");
        }
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) store.deleteEntry(ALIAS);
    }

    private SecretKey encryptionKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true).build());
        return generator.generateKey();
    }
}
