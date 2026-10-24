package com.autoquestion.mobile;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.URI;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;
import javax.net.ssl.HttpsURLConnection;

/** Separate from provider HTTP: never carries a model Authorization header or configuration. */
final class UpdateHttp {
    interface Connections { HttpsURLConnection open(URL url) throws Exception; }
    interface Progress { void received(long size, long total); }
    static final Connections SYSTEM = url -> (HttpsURLConnection) url.openConnection();
    private final Connections connections;
    private volatile HttpsURLConnection active;
    private volatile boolean cancelled;
    UpdateHttp(Connections connections) { this.connections = connections; }
    void cancel() { cancelled = true; HttpsURLConnection request = active; if (request != null) request.disconnect(); }
    void guard() throws Exception { if (cancelled || Thread.currentThread().isInterrupted()) throw new Exception("更新已取消"); }

    byte[] releaseMetadata() throws Exception {
        return read(UpdatePolicy.RELEASES_URL, 4 * 1024 * 1024, null, false, null, null);
    }
    byte[] asset(UpdatePolicy.Asset asset) throws Exception { return read(asset.url, asset.size, asset, true, null, null); }
    void download(UpdatePolicy.Asset asset, File file, Progress progress) throws Exception {
        read(asset.url, asset.size, asset, true, file, progress);
    }

    private byte[] read(String address, long maximum, UpdatePolicy.Asset asset, boolean redirects, File destination, Progress progress) throws Exception {
        HttpsURLConnection connection = null;
        try {
            if (asset != null && (!address.startsWith("https://github.com/" + UpdatePolicy.REPOSITORY + "/releases/download/")
                    || !UpdatePolicy.redirectAllowed(address))) throw new Exception("更新地址无效");
            guard();
            for (int hops = 0; ; hops++) {
                guard();
                connection = connections.open(new URL(address)); active = connection;
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(15000); connection.setReadTimeout(30000);
                connection.setRequestProperty("User-Agent", "AutoQuestion-Android-Updater");
                connection.setRequestProperty("Accept", redirects ? "application/octet-stream" : "application/vnd.github+json");
                if (!redirects) connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
                guard(); int status = connection.getResponseCode();
                if (status == 301 || status == 302 || status == 303 || status == 307 || status == 308) {
                    if (!redirects || hops >= 5) throw new Exception("更新跳转被拒绝");
                    String location = connection.getHeaderField("Location");
                    if (location == null) throw new Exception("更新地址无效");
                    String target = URI.create(address).resolve(location).toString();
                    if (!UpdatePolicy.redirectAllowed(target)) throw new Exception("更新跳转被拒绝");
                    connection.disconnect(); address = target; continue;
                }
                if (status != 200) throw new Exception("更新服务器暂不可用");
                long length = connection.getContentLengthLong();
                if (length > maximum || (asset != null && length >= 0 && length != asset.size)) throw new Exception("更新大小不一致");
                break;
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = connection.getInputStream();
                    ByteArrayOutputStream memory = destination == null ? new ByteArrayOutputStream() : null;
                    FileOutputStream file = destination == null ? null : new FileOutputStream(destination)) {
                byte[] buffer = new byte[32768]; long total = 0; int count;
                while ((count = input.read(buffer)) != -1) {
                    guard(); total += count;
                    if (total > maximum) throw new Exception("更新包超过限制");
                    digest.update(buffer, 0, count);
                    if (file != null) file.write(buffer, 0, count); else memory.write(buffer, 0, count);
                    if (progress != null) progress.received(total, maximum);
                }
                guard();
                if (asset != null && (total != asset.size || !hex(digest.digest()).equals(asset.sha256))) throw new Exception("更新校验失败");
                if (file != null) file.getFD().sync();
                return memory == null ? null : memory.toByteArray();
            }
        } finally { active = null; if (connection != null) connection.disconnect(); }
    }

    static void verifyFile(File file, UpdatePolicy.Asset expected) throws Exception {
        if (!file.isFile() || file.length() != expected.size) throw new Exception("更新大小不一致");
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new java.io.FileInputStream(file)) {
            byte[] buffer = new byte[32768]; int count;
            while ((count = input.read(buffer)) != -1) {
                if (Thread.currentThread().isInterrupted()) throw new Exception("更新已取消");
                digest.update(buffer, 0, count);
            }
        }
        if (!hex(digest.digest()).equals(expected.sha256)) throw new Exception("更新校验失败");
    }

    static String hex(byte[] digest) {
        StringBuilder value = new StringBuilder();
        for (byte item : digest) value.append(String.format(Locale.ROOT, "%02x", item & 255));
        return value.toString();
    }
}
