package com.autoquestion.mobile;

import android.accessibilityservice.AccessibilityService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.provider.Settings;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;

import java.util.concurrent.Executor;
import java.util.function.Consumer;

/** A user-enabled screenshot service with no accessibility event or gesture subscriptions. */
public final class RecognitionScreenshotService extends AccessibilityService {
    private static RecognitionScreenshotService connected;

    static RecognitionScreenshotService connected() { return connected; }

    static boolean isEnabled(Context context) {
        if (Build.VERSION.SDK_INT < 30) return false;
        String enabled = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        if (enabled == null) return false;
        ComponentName screenshotService = new ComponentName(context, RecognitionScreenshotService.class);
        for (String entry : enabled.split(":")) {
            if (screenshotService.equals(ComponentName.unflattenFromString(entry))) return true;
        }
        return false;
    }

    @Override protected void onServiceConnected() { connected = this; }

    @Override public boolean onUnbind(Intent intent) {
        if (connected == this) connected = null;
        return super.onUnbind(intent);
    }

    @Override public void onDestroy() {
        if (connected == this) connected = null;
        super.onDestroy();
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }

    void capture(Executor worker, Consumer<Bitmap> result) {
        if (Build.VERSION.SDK_INT < 30) { result.accept(null); return; }
        takeScreenshot(Display.DEFAULT_DISPLAY, worker, new TakeScreenshotCallback() {
            @Override public void onSuccess(ScreenshotResult screenshot) { result.accept(readFrame(screenshot)); }
            @Override public void onFailure(int errorCode) { result.accept(null); }
        });
    }

    private static Bitmap readFrame(ScreenshotResult screenshot) {
        if (Build.VERSION.SDK_INT < 30) return null;
        Bitmap pixels = null;
        try (HardwareBuffer buffer = screenshot.getHardwareBuffer()) {
            Bitmap hardware = Bitmap.wrapHardwareBuffer(buffer, screenshot.getColorSpace());
            if (hardware == null) return null;
            try { pixels = hardware.copy(Bitmap.Config.ARGB_8888, true); }
            finally { hardware.recycle(); }
            if (pixels == null || !hasContent(pixels)) return null;
            int width = pixels.getWidth(), height = pixels.getHeight();
            double scale = CaptureService.captureScale(width, height);
            if (scale == 1.0) {
                Bitmap frame = pixels;
                pixels = null;
                return frame;
            }
            int scaledWidth = Math.max(1, (int) Math.round(width * scale));
            int scaledHeight = Math.max(1, (int) Math.round(height * scale));
            Bitmap frame = Bitmap.createBitmap(scaledWidth, scaledHeight, Bitmap.Config.ARGB_8888);
            try {
                new Canvas(frame).drawBitmap(pixels, null, new Rect(0, 0, scaledWidth, scaledHeight), new Paint(Paint.FILTER_BITMAP_FLAG));
                return frame;
            } catch (RuntimeException error) {
                CaptureService.recycleFrame(frame);
                return null;
            }
        } catch (RuntimeException error) {
            return null;
        } finally { CaptureService.recycleFrame(pixels); }
    }

    private static boolean hasContent(Bitmap frame) {
        int width = frame.getWidth(), height = frame.getHeight();
        // A protected full-screen window may be black while the system bars remain visible.
        for (int y = height / 10; y < height - height / 10; y += 16) {
            for (int x = width / 10; x < width - width / 10; x += 16) {
                int color = frame.getPixel(x, y);
                if (Color.red(color) > 20 || Color.green(color) > 20 || Color.blue(color) > 20) return true;
            }
        }
        return false;
    }
}
