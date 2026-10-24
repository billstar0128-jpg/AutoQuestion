package com.autoquestion.mobile;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONArray;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Activity-owned updater. No background service, alarms, tokens, or provider client. */
final class UpdateManager implements AutoCloseable {
    interface Listener { void changed(State state); }
    static final class State {
        final String message;
        final UpdatePolicy.Release release;
        final boolean busy, ready, checking;
        State(String message, UpdatePolicy.Release release, boolean busy, boolean ready, boolean checking) {
            this.message = message; this.release = release; this.busy = busy; this.ready = ready; this.checking = checking;
        }
    }
    private final Context context;
    private final Listener listener;
    private final UpdateHttp.Connections connections;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final String installedVersion;
    private final long installedCode;
    private final File partial;
    private volatile UpdateHttp request;
    private Future<?> task;
    private UpdatePolicy.Release release;
    private boolean busy, ready, checking, closed, installerHandedOff;
    private long generation, lastCheck;
    private String message = "回到应用时自动检查，也可手动检查。";

    UpdateManager(Context context, Listener listener) { this(context, listener, UpdateHttp.SYSTEM); }
    UpdateManager(Context context, Listener listener, UpdateHttp.Connections connections) {
        this.context = context.getApplicationContext(); this.listener = listener; this.connections = connections;
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            installedVersion = info.versionName;
            installedCode = versionCode(info);
        } catch (PackageManager.NameNotFoundException error) { throw new IllegalStateException("无法读取当前版本"); }
        partial = new File(this.context.getCacheDir(), "updates/download-" + java.util.UUID.randomUUID() + ".apk.part");
        File[] oldParts = partial.getParentFile() == null ? null : partial.getParentFile().listFiles();
        if (oldParts != null) for (File file : oldParts) {
            if (file.getName().matches("download-[0-9a-f-]{36}\\.apk\\.part")
                    && System.currentTimeMillis() - file.lastModified() > 60 * 60 * 1000L) file.delete();
        }
        File old = readyFile(this.context);
        // An installer may still be reading its granted file after an Activity recreation.
        if (old.isFile() && System.currentTimeMillis() - old.lastModified() > 60 * 60 * 1000L) old.delete();
    }

    String currentVersion() { return installedVersion; }
    long currentCode() { return installedCode; }
    synchronized State state() { return new State(message, release, busy, ready, checking); }

    synchronized void check(boolean manual) {
        if (closed || busy || installerHandedOff) return;
        long now = android.os.SystemClock.elapsedRealtime();
        if (!manual && now - lastCheck < 60000 && lastCheck != 0) { emit(); return; }
        long operation = ++generation;
        lastCheck = now; busy = true; checking = true; message = "正在检查 GitHub 更新…"; emit();
        task = worker.submit(() -> {
            UpdateHttp http = new UpdateHttp(connections); request = http;
            try {
                if (!current(operation)) { http.cancel(); return; }
                String data = new String(http.releaseMetadata(), StandardCharsets.UTF_8);
                UpdatePolicy.Release found = UpdatePolicy.choose(new JSONArray(data), installedVersion);
                finish(operation, () -> {
                    if (ready && release != null && (found == null || (release.version.equals(found.version)
                            && release.apk.sha256.equals(found.apk.sha256) && release.apk.size == found.apk.size))) {
                        message = "已下载并验证 " + release.version + "，可点击安装，由系统确认。";
                        return;
                    }
                    if (ready) { ready = false; readyFile(context).delete(); }
                    release = found;
                    message = found == null ? "暂无更高的可安装版本（含测试版）。" : "发现 " + found.version
                            + (found.prerelease ? " · 测试版" : "") + "，点击下载后由系统确认安装。";
                });
            } catch (Exception error) { finish(operation, () -> message = "检查失败：网络不可用或 GitHub 限流，可稍后手动重试。识题不受影响。");
            } finally { if (request == http) request = null; }
        });
    }

    synchronized void download() {
        if (closed || busy || release == null || ready) return;
        UpdatePolicy.Release selected = release;
        long operation = ++generation;
        busy = true; checking = false; message = "正在下载 " + selected.version + " · 0%（仅应用缓存）"; emit();
        task = worker.submit(() -> {
            UpdateHttp http = new UpdateHttp(connections); request = http;
            try {
                if (!current(operation)) { http.cancel(); return; }
                File directory = partial.getParentFile();
                if (directory == null || (!directory.isDirectory() && !directory.mkdirs())) throw new Exception("缓存不可用");
                if (selected.checksums != null) {
                    String sums = new String(http.asset(selected.checksums), StandardCharsets.UTF_8);
                    UpdatePolicy.verifyChecksums(sums, selected.apk);
                }
                final int[] previous = {-1};
                http.download(selected.apk, partial, (bytes, total) -> {
                    int percent = (int) (bytes * 100 / total);
                    if (percent != previous[0]) {
                        previous[0] = percent;
                        synchronized (UpdateManager.this) {
                            if (current(operation)) { message = "正在下载 " + selected.version + " · " + percent + "%（仅应用缓存）"; emit(); }
                        }
                    }
                });
                http.guard(); verifyPackage(context, partial, selected.version);
                synchronized (UpdateManager.this) {
                    if (!current(operation)) return;
                    File finalFile = readyFile(context);
                    if (finalFile.exists() && !finalFile.delete()) throw new Exception("缓存不可用");
                    if (!partial.renameTo(finalFile)) throw new Exception("缓存不可用");
                    ready = true; busy = false; message = "已验证 " + selected.version + " 的摘要、包名和签名。点击安装，系统仍会要求你确认。"; emit();
                }
            } catch (Exception error) {
                finish(operation, () -> { ready = false; message = "下载或校验失败，已阻止安装。请检查网络后重试；当前版本与配置保持不变。"; });
            } finally {
                if (partial.exists()) partial.delete();
                if (request == http) request = null;
            }
        });
    }

    synchronized void cancel() {
        cancelWork(false);
    }

    private void cancelWork(boolean preserveReady) {
        if (closed) return;
        generation++; busy = false; checking = false;
        UpdateHttp current = request; if (current != null) current.cancel();
        if (task != null) task.cancel(true);
        if (!installerHandedOff && !preserveReady) { ready = false; discardFiles(); }
        message = preserveReady ? "更新检查已暂停，已验证的下载包仍可安装。" : "更新已取消，当前应用和配置保持不变。"; emit();
    }

    synchronized void pause() {
        if (busy) cancelWork(ready && checking); // Preserve an already verified package while ending metadata work.
    }

    synchronized void prepareInstall(Runnable verified) {
        if (!readyToInstall() || busy || release == null) return;
        long operation = ++generation;
        UpdatePolicy.Release selected = release;
        busy = true; checking = false; message = "正在再次验证安装包…"; emit();
        task = worker.submit(() -> {
            try {
                UpdateHttp.verifyFile(readyFile(context), selected.apk);
                verifyPackage(context, readyFile(context), selected.version);
                finish(operation, () -> message = "安装包已验证，等待系统确认。");
                main.post(() -> { if (current(operation) && readyToInstall()) verified.run(); });
            } catch (Exception error) {
                finish(operation, () -> { ready = false; discardFiles(); message = "安装包校验失败，已清除缓存。请重新下载。"; });
            }
        });
    }

    synchronized boolean readyToInstall() { return !closed && ready && readyFile(context).isFile(); }
    synchronized void handingToInstaller() { installerHandedOff = true; }
    synchronized void installerReturned() { installerHandedOff = false; }
    synchronized void installationNeedsPermission() {
        message = "请允许 AutoQuestion 安装应用；返回后再次点击“安装已下载更新”。不会自动安装。"; emit();
    }
    synchronized void installationFailed() {
        installerHandedOff = false; message = "系统安装未完成。可再次点击安装，或取消更新；不要卸载旧版。"; emit();
    }

    private synchronized boolean current(long operation) { return !closed && generation == operation; }
    private synchronized void finish(long operation, Runnable change) {
        if (!current(operation)) return;
        busy = false; checking = false; change.run(); emit();
    }
    private void emit() {
        State snapshot = state();
        long stamp = generation;
        main.post(() -> { synchronized (UpdateManager.this) { if (!closed && generation == stamp) listener.changed(snapshot); } });
    }

    static long versionCode(PackageInfo info) { return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode; }
    static void verifyPackage(Context context, File file, String expectedVersion) throws Exception {
        PackageManager packages = context.getPackageManager();
        int flags = Build.VERSION.SDK_INT >= 28 ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
        PackageInfo installed = packages.getPackageInfo(context.getPackageName(), flags);
        PackageInfo archive = packages.getPackageArchiveInfo(file.getAbsolutePath(), flags);
        if (archive == null || !context.getPackageName().equals(archive.packageName)
                || !expectedVersion.equals(archive.versionName) || versionCode(archive) <= versionCode(installed)
                || UpdatePolicy.compare(archive.versionName, installed.versionName) <= 0
                || archive.applicationInfo == null || archive.applicationInfo.minSdkVersion > Build.VERSION.SDK_INT) {
            throw new Exception("更新包版本或包名不匹配");
        }
        if (!signatures(installed).equals(signatures(archive))) throw new Exception("更新包签名不同");
    }

    @SuppressWarnings("deprecation")
    private static Set<String> signatures(PackageInfo info) throws Exception {
        Signature[] values = Build.VERSION.SDK_INT >= 28 && info.signingInfo != null
                ? info.signingInfo.getApkContentsSigners() : info.signatures;
        if (values == null || values.length == 0) throw new Exception("签名不可用");
        Set<String> result = new HashSet<>();
        for (Signature value : values) result.add(UpdateHttp.hex(java.security.MessageDigest.getInstance("SHA-256").digest(value.toByteArray())));
        return result;
    }

    static File readyFile(Context context) { return new File(context.getCacheDir(), "updates/AutoQuestion.apk"); }
    private void discardFiles() { readyFile(context).delete(); partial.delete(); }

    @Override public synchronized void close() {
        if (closed) return;
        cancel(); closed = true;
        worker.shutdownNow(); main.removeCallbacksAndMessages(null);
    }
}
