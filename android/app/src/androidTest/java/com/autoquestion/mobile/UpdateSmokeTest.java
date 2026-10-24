package com.autoquestion.mobile;

import android.app.UiAutomation;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.test.InstrumentationTestCase;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.security.cert.Certificate;
import java.util.ArrayDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.HttpsURLConnection;

/** Synthetic releases and real APKs, restricted to an owned disposable emulator.
 * Generate APK assets with tools/build_android_app.ps1 -UpdateTestFixtures; they stay ignored.
 * Run testPrepareSystemInstaller separately; host confirms the OS Update button after it ends,
 * then runs testUpgradePreservesConfiguration in the newly installed app process.
 */
@SuppressWarnings("deprecation")
public final class UpdateSmokeTest extends InstrumentationTestCase {
    private static final String VERSION = "0.6.0";
    private static final String NAME = "AutoQuestion-" + VERSION + "-Android.apk";
    private static final String APK_URL = "https://github.com/" + UpdatePolicy.REPOSITORY + "/releases/download/v" + VERSION + "/" + NAME;
    private static final String KEY = "synthetic-update-test-key-no-account";
    private Context context;
    private UiAutomation automation;

    @Override protected void setUp() throws Exception {
        super.setUp();
        assertTrue("Updates must never control a personal phone", "ranchu".equals(android.os.Build.HARDWARE)
                || "goldfish".equals(android.os.Build.HARDWARE));
        context = getInstrumentation().getTargetContext();
        automation = getInstrumentation().getUiAutomation();
        android.accessibilityservice.AccessibilityServiceInfo info = automation.getServiceInfo();
        info.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        automation.setServiceInfo(info);
    }

    public void testVerifiedDownloadSecurityCancellationAndProvider() throws Exception {
        byte[] apk = asset("update-same-signer.apk");
        AtomicInteger metadata = new AtomicInteger(), downloads = new AtomicInteger();
        UpdateHttp.Connections network = url -> {
            if (url.toString().equals(UpdatePolicy.RELEASES_URL)) { metadata.incrementAndGet(); return new Response(url, releaseJson(apk)); }
            if (url.toString().equals(APK_URL)) { downloads.incrementAndGet(); return new Response(url, apk); }
            throw new IOException("Unexpected test destination");
        };
        UpdateManager manager = new UpdateManager(context, state -> {}, network);
        File ready = UpdateManager.readyFile(context);
        try {
            manager.check(false); awaitIdle(manager);
            assertEquals(VERSION, manager.state().release.version);
            assertEquals("Checking must not download the APK", 0, downloads.get());
            manager.check(false); SystemClock.sleep(80); assertEquals("Automatic polling must be throttled", 1, metadata.get());
            manager.check(true); awaitIdle(manager); assertEquals("Manual check bypasses the automatic cooldown", 2, metadata.get());
            manager.download(); awaitIdle(manager); assertTrue(manager.state().message, manager.readyToInstall());
            manager.check(true); awaitIdle(manager);
            assertTrue("A metadata recheck must retain a still-current verified APK", manager.readyToInstall());
            assertEquals("Rechecking must not redownload a current ready APK", 1, downloads.get());
            UpdateManager.verifyPackage(context, ready, VERSION);
            assertEquals(apk.length, ready.length());
            try (InputStream stream = context.getContentResolver().openInputStream(UpdatePackageProvider.uri(context))) {
                assertNotNull(stream); assertEquals(apk.length, read(stream).length);
            }
            for (String mode : new String[]{"w", "rw", "rwt"}) {
                try (ParcelFileDescriptor unexpected = context.getContentResolver().openFileDescriptor(UpdatePackageProvider.uri(context), mode)) {
                    fail("Provider must reject write mode " + mode);
                } catch (java.io.FileNotFoundException expected) { /* rejected */ }
            }
            for (Uri uri : new Uri[]{UpdatePackageProvider.uri(context).buildUpon().appendQueryParameter("path", "settings").build(),
                    Uri.parse("content://" + context.getPackageName() + ".updates/apk/../settings.xml")}) {
                try (InputStream unexpected = context.getContentResolver().openInputStream(uri)) { fail("Provider exposed a nonfixed URI"); }
                catch (java.io.FileNotFoundException expected) { /* rejected */ }
            }
            // A malicious local replacement between download and installation must be rejected.
            try (FileOutputStream output = new FileOutputStream(ready, true)) { output.write(1); }
            AtomicInteger installed = new AtomicInteger();
            manager.prepareInstall(installed::incrementAndGet); awaitIdle(manager); getInstrumentation().waitForIdleSync();
            assertFalse(manager.readyToInstall()); assertEquals(0, installed.get()); assertFalse(ready.exists());
        } finally { manager.close(); }

        File candidate = new File(context.getCacheDir(), "update-package-check.apk");
        try {
            copy(apk, candidate); assertPackageRejected(candidate, "0.7.0");
            copy(asset("update-wrong-signer.apk"), candidate); assertPackageRejected(candidate, VERSION);
            copy(asset("update-wrong-package.apk"), candidate); assertPackageRejected(candidate, VERSION);
            try (InputStream installed = new java.io.FileInputStream(context.getApplicationInfo().sourceDir)) { copy(read(installed), candidate); }
            assertPackageRejected(candidate, "0.5.0");
        } finally { candidate.delete(); }

        byte[] corrupt = apk.clone(); corrupt[corrupt.length - 1] ^= 1;
        UpdateManager bad = new UpdateManager(context, state -> {}, url -> new Response(url,
                url.toString().equals(UpdatePolicy.RELEASES_URL) ? releaseJson(apk) : corrupt));
        try { bad.check(true); awaitIdle(bad); bad.download(); awaitIdle(bad); assertFalse(bad.readyToInstall()); assertFalse(ready.exists()); }
        finally { bad.close(); }

        CountDownLatch entered = new CountDownLatch(1), cancelled = new CountDownLatch(1);
        UpdateManager slow = new UpdateManager(context, state -> {}, url -> {
            if (url.toString().equals(UpdatePolicy.RELEASES_URL)) return new Response(url, releaseJson(apk));
            return new Response(url, apk) {
                @Override public InputStream getInputStream() {
                    return new ByteArrayInputStream(apk) {
                        @Override public synchronized int read(byte[] bytes, int offset, int length) {
                            entered.countDown();
                            try { cancelled.await(10, TimeUnit.SECONDS); } catch (InterruptedException error) { Thread.currentThread().interrupt(); }
                            return super.read(bytes, offset, length);
                        }
                    };
                }
                @Override public void disconnect() { cancelled.countDown(); super.disconnect(); }
            };
        });
        try {
            slow.check(true); awaitIdle(slow); slow.download(); assertTrue(entered.await(5, TimeUnit.SECONDS));
            slow.pause(); assertFalse(slow.state().busy); assertTrue(cancelled.await(5, TimeUnit.SECONDS));
            long deadline = SystemClock.uptimeMillis() + 5000;
            while (hasPartials() && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(20);
            assertFalse("Cancelled partial APKs must be removed", hasPartials());
            assertFalse(slow.readyToInstall()); assertFalse(ready.exists());
        } finally { slow.close(); }

        AtomicInteger foreign = new AtomicInteger();
        UpdateHttp redirected = new UpdateHttp(url -> {
            if (!APK_URL.equals(url.toString())) { foreign.incrementAndGet(); throw new IOException("Foreign request"); }
            return new Response(url, new byte[0]) {
                @Override public int getResponseCode() { return 302; }
                @Override public String getHeaderField(String name) { return "Location".equals(name) ? "https://example.com/private.apk" : null; }
            };
        });
        try { redirected.asset(apkAsset(apk)); fail("Foreign CDN redirect accepted"); } catch (Exception expected) { /* rejected before connecting */ }
        assertEquals(0, foreign.get());
        assertFalse("Update tests must not start projection", CaptureService.isRunning());
    }

    public void testPrepareSystemInstaller() throws Exception {
        byte[] apk = asset("update-same-signer.apk");
        AtomicInteger checks = new AtomicInteger();
        MockHttps.install(url -> {
            if (UpdatePolicy.RELEASES_URL.equals(url.toString())) { checks.incrementAndGet(); return new Response(url, releaseJson(apk)); }
            if (APK_URL.equals(url.toString())) return new Response(url, apk);
            throw new IOException("Unexpected test destination");
        });
        SecureStore store = new SecureStore(context);
        store.save(new ApiConfig("https://synthetic.autoquestion.invalid/v1", "upgrade-keeps-model"), KEY);
        assertTrue(context.getSharedPreferences("update_smoke", Context.MODE_PRIVATE).edit()
                .putInt("uid", android.os.Process.myUid()).commit());
        MainActivity activity = (MainActivity) getInstrumentation().startActivitySync(new Intent(context, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_MULTIPLE_TASK));
        awaitView(activity, "下载 " + VERSION, 10000);
        int initialChecks = checks.get();
        assertTrue("Activity startup must check releases", initialChecks >= 1);
        clickView(activity, "检查更新"); awaitCount(checks, initialChecks + 1);
        awaitView(activity, "下载 " + VERSION, 5000); clickView(activity, "下载 " + VERSION);
        awaitView(activity, "安装已下载更新", 15000); clickView(activity, "安装已下载更新");
        if (!context.getPackageManager().canRequestPackageInstalls()) {
            assertTrue("Unknown-source permission page must be user-visible", awaitUi("Allow from this source", 10000));
            assertTrue("The test user must explicitly allow this source", clickUi("Allow from this source"));
            long deadline = SystemClock.uptimeMillis() + 5000;
            while (!context.getPackageManager().canRequestPackageInstalls() && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(50);
            assertTrue(context.getPackageManager().canRequestPackageInstalls());
            shell("input keyevent KEYCODE_BACK");
            awaitView(activity, "安装已下载更新", 10000);
            assertTrue("Returning from Settings must not silently start installation", awaitUi("检查更新", 5000));
            clickView(activity, "安装已下载更新");
        }
        assertTrue("Actual Android installation confirmation must appear", awaitUi("Do you want to update this app?", 15000));
        assertTrue("The system must retain an explicit Update action", awaitUi("Update", 5000));
        assertFalse(CaptureService.isRunning());
        assertEquals("The app must remain at 0.5 until the user confirms", "0.5.0",
                context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName);
        // Deliberately leave installer open. The host confirms it after this process reports OK.
    }

    public void testUpgradePreservesConfiguration() throws Exception {
        assertEquals("0.6.0", context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName);
        assertEquals("Installing an update must keep the application UID", android.os.Process.myUid(),
                context.getSharedPreferences("update_smoke", Context.MODE_PRIVATE).getInt("uid", -1));
        SecureStore store = new SecureStore(context);
        assertEquals("upgrade-keeps-model", store.config().model);
        assertEquals(KEY, store.readKey(store.config()));
        assertFalse(CaptureService.isRunning());
        store.forget(); context.getSharedPreferences("update_smoke", Context.MODE_PRIVATE).edit().clear().commit();
        UpdateManager.readyFile(context).delete();
    }

    private boolean hasPartials() {
        File directory = UpdateManager.readyFile(context).getParentFile();
        File[] files = directory == null ? null : directory.listFiles();
        if (files != null) for (File file : files) if (file.getName().endsWith(".part")) return true;
        return false;
    }
    private void assertPackageRejected(File candidate, String version) {
        try { UpdateManager.verifyPackage(context, candidate, version); fail("Unsafe APK accepted"); }
        catch (Exception expected) { /* fail() is AssertionError and cannot be swallowed */ }
    }
    private static void awaitIdle(UpdateManager manager) {
        long deadline = SystemClock.uptimeMillis() + 20000;
        while (manager.state().busy && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(25);
        assertFalse("Update operation timed out", manager.state().busy);
    }
    private static void awaitCount(AtomicInteger value, int count) {
        long deadline = SystemClock.uptimeMillis() + 5000;
        while (value.get() < count && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(20);
        assertTrue("Expected at least " + count + " release checks", value.get() >= count);
    }
    private static byte[] releaseJson(byte[] apk) throws IOException {
        try {
            JSONObject asset = new JSONObject().put("name", NAME).put("browser_download_url", APK_URL)
                    .put("size", apk.length).put("state", "uploaded").put("digest", "sha256:" + sha(apk));
            return new JSONArray().put(new JSONObject().put("tag_name", "v" + VERSION).put("draft", false)
                    .put("prerelease", true).put("assets", new JSONArray().put(asset))).toString().getBytes(StandardCharsets.UTF_8);
        } catch (Exception error) { throw new IOException(error); }
    }
    private static UpdatePolicy.Asset apkAsset(byte[] apk) throws Exception { return new UpdatePolicy.Asset(NAME, APK_URL, sha(apk), apk.length); }
    private static String sha(byte[] bytes) throws Exception { return UpdateHttp.hex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes)); }
    private byte[] asset(String name) throws Exception { try (InputStream stream = getInstrumentation().getContext().getAssets().open(name)) { return read(stream); } }
    private static byte[] read(InputStream stream) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream(); byte[] buffer = new byte[8192]; int count;
        while ((count = stream.read(buffer)) != -1) output.write(buffer, 0, count);
        return output.toByteArray();
    }
    private static void copy(byte[] bytes, File destination) throws IOException { try (FileOutputStream out = new FileOutputStream(destination)) { out.write(bytes); } }
    private void clickView(MainActivity activity, String text) {
        getInstrumentation().runOnMainSync(() -> {
            View target = find(activity.getWindow().getDecorView(), text);
            assertNotNull("Missing action " + text, target); assertTrue(target.isEnabled()); target.performClick();
        });
    }
    private void awaitView(MainActivity activity, String text, long timeout) {
        long deadline = SystemClock.uptimeMillis() + timeout; boolean[] found = {false};
        while (!found[0] && SystemClock.uptimeMillis() < deadline) {
            getInstrumentation().runOnMainSync(() -> { View view = find(activity.getWindow().getDecorView(), text); found[0] = view != null && view.getVisibility() == View.VISIBLE && view.isEnabled(); });
            if (!found[0]) SystemClock.sleep(25);
        }
        assertTrue("Missing enabled action " + text, found[0]);
    }
    private static View find(View view, String text) {
        if (view instanceof TextView && text.contentEquals(((TextView) view).getText())) return view;
        if (view instanceof ViewGroup) for (int i = 0; i < ((ViewGroup) view).getChildCount(); i++) { View found = find(((ViewGroup) view).getChildAt(i), text); if (found != null) return found; }
        return null;
    }
    private boolean awaitUi(String text, long timeout) {
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (SystemClock.uptimeMillis() < deadline) { if (uiNode(text) != null) return true; SystemClock.sleep(50); }
        return false;
    }
    private AccessibilityNodeInfo uiNode(String text) {
        for (android.view.accessibility.AccessibilityWindowInfo window : automation.getWindows()) {
            AccessibilityNodeInfo root = window.getRoot(); if (root == null) continue;
            ArrayDeque<AccessibilityNodeInfo> nodes = new ArrayDeque<>(); nodes.add(root);
            while (!nodes.isEmpty()) {
                AccessibilityNodeInfo node = nodes.remove();
                if (node.getText() != null && text.equalsIgnoreCase(node.getText().toString())) return node;
                for (int i = 0; i < node.getChildCount(); i++) {
                    AccessibilityNodeInfo child = node.getChild(i);
                    if (child != null) nodes.add(child);
                }
            }
        }
        return null;
    }
    private boolean clickUi(String text) {
        AccessibilityNodeInfo node = uiNode(text);
        while (node != null && !node.isClickable()) node = node.getParent();
        return node != null && node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
    }
    private String shell(String command) throws Exception { try (ParcelFileDescriptor descriptor = automation.executeShellCommand(command);
            InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(descriptor)) { return new String(read(input), StandardCharsets.UTF_8); } }

    static class Response extends HttpsURLConnection {
        final byte[] bytes;
        Response(URL url, byte[] bytes) { super(url); this.bytes = bytes; }
        @Override public InputStream getInputStream() { return new ByteArrayInputStream(bytes); }
        @Override public long getContentLengthLong() { return bytes.length; }
        @Override public int getResponseCode() {
            assertNull("Updater requests must never carry a model API Key", getRequestProperty("Authorization"));
            return 200;
        }
        @Override public void disconnect() { connected = false; }
        @Override public boolean usingProxy() { return false; }
        @Override public void connect() { connected = true; }
        @Override public String getCipherSuite() { return "SYNTHETIC"; }
        @Override public Certificate[] getLocalCertificates() { return null; }
        @Override public Certificate[] getServerCertificates() { return null; }
        @Override public Principal getPeerPrincipal() { return null; }
        @Override public Principal getLocalPrincipal() { return null; }
    }
}
