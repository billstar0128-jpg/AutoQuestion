package com.autoquestion.mobile;

import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.test.InstrumentationTestCase;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import java.security.Principal;
import java.security.cert.Certificate;
import java.util.ArrayDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.HttpsURLConnection;

/** Runs only on an explicitly selected, disposable emulator. All HTTPS is replaced in memory. */
@SuppressWarnings("deprecation")
public final class MobileSmokeTest extends InstrumentationTestCase {
    private static final AtomicInteger requests = new AtomicInteger();
    private static final AtomicInteger cancelledRequests = new AtomicInteger();
    private static volatile CountDownLatch requestEntered = new CountDownLatch(1);
    private static volatile CountDownLatch answerAllowed = new CountDownLatch(1);
    private static volatile byte[] capturedRequest;
    private MainActivity activity;
    private Context context;
    private UiAutomation automation;

    public void testRealProjectionOverlaySixQuestionsAndStop() throws Exception {
        Instrumentation instrumentation = getInstrumentation();
        context = instrumentation.getTargetContext();
        automation = instrumentation.getUiAutomation();
        android.accessibilityservice.AccessibilityServiceInfo info = automation.getServiceInfo();
        info.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
                | android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
        automation.setServiceInfo(info);
        // Reject any unexpected destination. No model credentials or real API are used.
        URL.setURLStreamHandlerFactory(protocol -> "https".equals(protocol) ? new URLStreamHandler() {
            @Override protected URLConnection openConnection(URL url) throws IOException {
                if (!"synthetic.autoquestion.invalid".equals(url.getHost())) throw new IOException("Unexpected test destination");
                return new FakeConnection(url);
            }
        } : null);
        shell("appops set com.autoquestion.mobile SYSTEM_ALERT_WINDOW allow");
        shell("pm grant com.autoquestion.mobile android.permission.POST_NOTIFICATIONS");
        SecureStore store = new SecureStore(context);
        store.save(new ApiConfig("https://synthetic.autoquestion.invalid/v1", "synthetic-vision"), "synthetic-test-key-no-account");
        activity = (MainActivity) instrumentation.startActivitySync(new Intent(context, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        try {
            startAndConsent();
            showSyntheticQuestions();
            assertTrue("Small overlay must be accessible", clickText("AQ", false));
            assertTrue("A real projected frame must reach the in-memory fake API", requestEntered.await(15, TimeUnit.SECONDS));
            assertEquals(1, requests.get());
            int[] portrait = verifyCapturedRequest();
            assertTrue("Initial capture must be portrait", portrait[1] > portrait[0]);
            // Repeated taps while busy must neither capture again nor queue another request.
            awaitText("···", 5000);
            for (int i = 0; i < 5; i++) clickText("···", false);
            SystemClock.sleep(200);
            assertEquals("Busy taps must not enqueue work", 1, requests.get());
            answerAllowed.countDown();
            awaitText("第 1 题 · 单选", 15000);
            assertTrue("First answer must be shown", containsText("A · Alpha"));
            boolean sixth = false;
            for (int i = 0; i < 8; i++) {
                if (containsText("第 6 题 · 判断")) { sixth = true; break; }
                scrollAnswerPanel();
            }
            assertTrue("All six separate mixed-type answers must be present", sixth);
            SystemClock.sleep(300);
            assertEquals("Completing one screen must not run queued duplicate work", 1, requests.get());
            assertTrue(clickText("收起", false));
            Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(MainActivity.class.getName(), null, false);
            automation.setRotation(UiAutomation.ROTATION_FREEZE_90);
            MainActivity rotated = (MainActivity) monitor.waitForActivityWithTimeout(5000);
            instrumentation.removeMonitor(monitor);
            if (rotated != null) activity = rotated;
            assertTrue("Rotating must keep the same approved projection session", CaptureService.isRunning());
            requestEntered = new CountDownLatch(1); answerAllowed = new CountDownLatch(1);
            showSyntheticQuestions();
            assertTrue(clickText("AQ", false));
            assertTrue("A landscape frame must be captured", requestEntered.await(15, TimeUnit.SECONDS));
            int[] landscape = verifyCapturedRequest();
            assertTrue("Projection must resize to landscape", landscape[0] > landscape[1]);
            assertEquals(2, requests.get());
            answerAllowed.countDown();
            awaitText("第 1 题 · 单选", 15000);
            assertTrue("Answer panel has a stop action", clickText("停止", false));
            awaitStopped();
            assertFalse("Projection grant must be released", shell("dumpsys media_projection").contains("com.autoquestion.mobile"));

            // A fresh consent is obtained for a new session. Cancelling an active request releases it.
            requestEntered = new CountDownLatch(1);
            answerAllowed = new CountDownLatch(1);
            instrumentation.runOnMainSync(() -> activity.finish());
            activity = (MainActivity) instrumentation.startActivitySync(new Intent(context, MainActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            startAndConsent();
            // Cancellation needs only an owned, public emulator screen; the six-question fixture
            // has already been checked in both orientations in the preceding session.
            shell("input keyevent KEYCODE_HOME");
            awaitText("Phone", 5000);
            assertTrue(clickText("AQ", false));
            assertTrue(requestEntered.await(15, TimeUnit.SECONDS));
            assertEquals(3, requests.get());
            awaitText("···", 5000);
            assertTrue("Long press opens controls while analysis is pending", clickText("···", true));
            awaitText("停止", 5000);
            assertTrue(clickText("停止", false));
            awaitStopped();
            long deadline = SystemClock.uptimeMillis() + 5000;
            while (cancelledRequests.get() == 0 && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(50);
            assertEquals("Stopping must cancel the in-flight API request", 1, cancelledRequests.get());
            assertEquals("Screenshot files must not exist in app files", 0, screenshotFiles(context.getFilesDir()));
            assertEquals("Screenshot files must not exist in app cache", 0, screenshotFiles(context.getCacheDir()));
            assertFalse("No screenshot is written to shared DCIM/Pictures", shell(
                    "find /sdcard/DCIM /sdcard/Pictures -type f 2>/dev/null").matches("(?s).+\\.(png|jpe?g).*"));
        } finally {
            answerAllowed.countDown();
            context.stopService(new Intent(context, CaptureService.class));
            if (activity != null) instrumentation.runOnMainSync(() -> activity.finish());
            automation.setRotation(UiAutomation.ROTATION_UNFREEZE);
            store.forget();
            if (capturedRequest != null) java.util.Arrays.fill(capturedRequest, (byte) 0);
        }
    }

    private void startAndConsent() throws Exception {
        getInstrumentation().runOnMainSync(() -> {
            View button = findView(activity.getWindow().getDecorView(), "开启悬浮识题  ↗");
            assertNotNull("Start action must exist", button);
            button.performClick();
        });
        long deadline = SystemClock.uptimeMillis() + 15000;
        while (!CaptureService.isRunning() && SystemClock.uptimeMillis() < deadline) {
            for (String consent : new String[]{"Start now", "Share screen", "Start", "立即开始", "开始共享", "共享屏幕"}) {
                if (clickText(consent, false)) break;
            }
            SystemClock.sleep(100);
        }
        assertTrue("The system-approved projection session must start; visible: " + visibleText(), CaptureService.isRunning());
        awaitText("AQ", 5000);
    }

    private void showSyntheticQuestions() throws Exception {
        Instrumentation.ActivityMonitor monitor = getInstrumentation().addMonitor(MainActivity.class.getName(), null, false);
        shell("am start -n com.autoquestion.mobile/.MainActivity -f 0x20000");
        MainActivity resumed = (MainActivity) monitor.waitForActivityWithTimeout(1000);
        getInstrumentation().removeMonitor(monitor);
        if (resumed != null) activity = resumed;
        getInstrumentation().runOnMainSync(() -> {
            // The real setup screen is secure. Only this disposable test replaces it with public fixtures.
            activity.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
            TextView fixture = new TextView(activity);
            fixture.setTextColor(Color.BLACK); fixture.setBackgroundColor(Color.CYAN); fixture.setTextSize(15);
            fixture.setPadding(8, 40, 8, 8);
            fixture.setText("Synthetic questions — no private screen\n\n1. Single: Alpha?\nA Alpha   B Beta\n\n"
                    + "2. Multiple: Alpha and Gamma?\nA Alpha   B Beta   C Gamma\n\n"
                    + "3. True/False: one equals one?\nTrue   False\n\n"
                    + "4. Single: Alpha?\nA Alpha   B Beta\n\n"
                    + "5. Multiple: Alpha and Gamma?\nA Alpha   B Beta   C Gamma\n\n"
                    + "6. True/False: one equals one?\nTrue   False");
            activity.setContentView(fixture);
        });
        getInstrumentation().waitForIdleSync();
        awaitText("Synthetic questions", 5000);
    }

    private int[] verifyCapturedRequest() throws Exception {
        JSONObject body = new JSONObject(new String(capturedRequest, java.nio.charset.StandardCharsets.UTF_8));
        assertEquals("synthetic-vision", body.getString("model"));
        String image = body.getJSONArray("messages").getJSONObject(1).getJSONArray("content")
                .getJSONObject(1).getJSONObject("image_url").getString("url");
        assertTrue(image.startsWith("data:image/png;base64,"));
        byte[] bytes = android.util.Base64.decode(image.substring(image.indexOf(',') + 1), android.util.Base64.DEFAULT);
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        assertNotNull("A real PNG must be captured", bitmap);
        int width = bitmap.getWidth(), height = bitmap.getHeight();
        assertTrue(width > 0 && height > 0);
        int cyan = 0, samples = 0;
        for (int y = 0; y < height; y += 8) for (int x = 0; x < width; x += 8) {
            int color = bitmap.getPixel(x, y);
            if (Color.red(color) < 20 && Color.green(color) > 220 && Color.blue(color) > 220) cyan++;
            samples++;
        }
        assertTrue("The capture must show the synthetic cyan fixture, not another window; cyan=" + cyan + "/" + samples
                + "; centre=" + Integer.toHexString(bitmap.getPixel(width / 2, height / 2)), cyan > samples / 4);
        bitmap.recycle(); java.util.Arrays.fill(bytes, (byte) 0);
        return new int[]{width, height};
    }

    private static View findView(View view, String text) {
        if (view instanceof TextView && text.contentEquals(((TextView) view).getText())) return view;
        if (view instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                View match = findView(group.getChildAt(i), text);
                if (match != null) return match;
            }
        }
        return null;
    }

    private AccessibilityNodeInfo node(String text) {
        AccessibilityNodeInfo partial = null;
        for (AccessibilityNodeInfo root : roots()) for (AccessibilityNodeInfo match : root.findAccessibilityNodeInfosByText(text)) {
            if (match.getText() == null) continue;
            String value = match.getText().toString();
            if (value.equalsIgnoreCase(text)) return match;
            if (partial == null && value.toLowerCase(java.util.Locale.ROOT)
                    .contains(text.toLowerCase(java.util.Locale.ROOT))) partial = match;
        }
        return partial;
    }

    private boolean clickText(String text, boolean longClick) {
        AccessibilityNodeInfo match = node(text);
        return match != null && match.performAction(longClick ? AccessibilityNodeInfo.ACTION_LONG_CLICK : AccessibilityNodeInfo.ACTION_CLICK);
    }

    private boolean containsText(String text) { return node(text) != null; }

    private void awaitText(String text, long timeout) {
        long deadline = SystemClock.uptimeMillis() + timeout;
        while (!containsText(text) && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(50);
        assertTrue("Expected UI text: " + text + "; visible: " + visibleText(), containsText(text));
    }

    private void scrollAnswerPanel() {
        ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<>(roots());
        while (!queue.isEmpty()) {
            AccessibilityNodeInfo item = queue.remove();
            if (item.isScrollable()) { item.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD); SystemClock.sleep(100); return; }
            for (int i = 0; i < item.getChildCount(); i++) if (item.getChild(i) != null) queue.add(item.getChild(i));
        }
    }

    private String visibleText() {
        ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<>(roots());
        StringBuilder text = new StringBuilder();
        while (!queue.isEmpty()) {
            AccessibilityNodeInfo item = queue.remove();
            if (item.getText() != null) text.append(item.getText()).append(" | ");
            for (int i = 0; i < item.getChildCount(); i++) if (item.getChild(i) != null) queue.add(item.getChild(i));
        }
        return text.toString();
    }

    private void awaitStopped() {
        long deadline = SystemClock.uptimeMillis() + 5000;
        while (CaptureService.isRunning() && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(50);
        assertFalse("Service must stop", CaptureService.isRunning());
        while (bubblePresent() && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(50);
        assertFalse("Floating button must be removed", bubblePresent());
    }

    private boolean bubblePresent() {
        for (AccessibilityNodeInfo root : roots()) for (AccessibilityNodeInfo candidate : root.findAccessibilityNodeInfosByText("AQ")) {
            if (candidate.getContentDescription() != null
                    && candidate.getContentDescription().toString().startsWith("AutoQuestion，轻点识题")) return true;
        }
        return false;
    }

    private java.util.List<AccessibilityNodeInfo> roots() {
        java.util.List<AccessibilityNodeInfo> roots = new java.util.ArrayList<>();
        for (android.view.accessibility.AccessibilityWindowInfo window : automation.getWindows()) {
            AccessibilityNodeInfo root = window.getRoot();
            if (root != null) roots.add(root);
        }
        if (roots.isEmpty()) {
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            if (root != null) roots.add(root);
        }
        return roots;
    }

    private String shell(String command) throws IOException {
        try (ParcelFileDescriptor descriptor = automation.executeShellCommand(command);
             InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(descriptor);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            return output.toString("UTF-8");
        }
    }

    private int screenshotFiles(java.io.File directory) {
        int count = 0;
        java.io.File[] children = directory.listFiles();
        if (children != null) for (java.io.File file : children) {
            if (file.isDirectory()) count += screenshotFiles(file);
            else if (file.getName().matches("(?i).+\\.(png|jpe?g|webp)")) count++;
        }
        return count;
    }

    private static String response() throws Exception {
        JSONArray results = new JSONArray();
        for (int i = 0; i < 6; i++) {
            String type = i % 3 == 0 ? "single_choice" : i % 3 == 1 ? "multiple_choice" : "true_false";
            JSONArray options = new JSONArray();
            boolean tf = type.equals("true_false");
            options.put(new JSONObject().put("index", 0).put("label", tf ? JSONObject.NULL : "A").put("text", tf ? "True" : "Alpha"));
            options.put(new JSONObject().put("index", 1).put("label", tf ? JSONObject.NULL : "B").put("text", tf ? "False" : "Beta"));
            JSONObject answer = new JSONObject().put("question_type", type).put("confidence", .9).put("short_reason", "Synthetic fixture");
            if (type.equals("multiple_choice")) {
                options.put(new JSONObject().put("index", 2).put("label", "C").put("text", "Gamma"));
                answer.put("selected_indices", new JSONArray().put(0).put(2)).put("selected_labels", new JSONArray().put("A").put("C"))
                        .put("selected_texts", new JSONArray().put("Alpha").put("Gamma"));
            } else answer.put("selected_index", 0).put("selected_label", tf ? JSONObject.NULL : "A").put("selected_text", tf ? "True" : "Alpha");
            results.put(new JSONObject().put("question", new JSONObject().put("question_text", "Synthetic question " + (i + 1))
                    .put("question_type", type).put("source_type", "VISION").put("options", options)).put("answer", answer));
        }
        return new JSONObject().put("choices", new JSONArray().put(new JSONObject().put("finish_reason", "stop")
                .put("message", new JSONObject().put("content", new JSONObject().put("results", results).toString())))).toString();
    }

    private static final class FakeConnection extends HttpsURLConnection {
        private final ByteArrayOutputStream body = new ByteArrayOutputStream();
        private volatile boolean disconnected;
        FakeConnection(URL url) { super(url); }
        @Override public OutputStream getOutputStream() { return body; }
        @Override public int getResponseCode() throws IOException {
            capturedRequest = body.toByteArray(); requests.incrementAndGet(); requestEntered.countDown();
            try { if (!answerAllowed.await(30, TimeUnit.SECONDS) || disconnected) throw new IOException("Test cancelled"); }
            catch (InterruptedException e) { throw new IOException("Test interrupted"); }
            return 200;
        }
        @Override public InputStream getInputStream() throws IOException {
            try { return new ByteArrayInputStream(response().getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
            catch (Exception e) { throw new IOException("Fixture failed", e); }
        }
        @Override public void disconnect() {
            disconnected = true;
            if (answerAllowed.getCount() > 0) { cancelledRequests.incrementAndGet(); answerAllowed.countDown(); }
            byte[] memory = body.toByteArray(); java.util.Arrays.fill(memory, (byte) 0); body.reset();
        }
        @Override public void connect() { }
        @Override public boolean usingProxy() { return false; }
        @Override public String getCipherSuite() { return "TEST_ONLY"; }
        @Override public Certificate[] getLocalCertificates() { return null; }
        @Override public Certificate[] getServerCertificates() { return new Certificate[0]; }
        @Override public Principal getPeerPrincipal() { return null; }
        @Override public Principal getLocalPrincipal() { return null; }
    }
}
