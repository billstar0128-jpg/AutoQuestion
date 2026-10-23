package com.autoquestion.mobile;

import android.app.Activity;
import android.app.Dialog;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.ClipData;
import android.content.ClipDescription;
import android.content.ClipboardManager;
import android.content.pm.ServiceInfo;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Looper;
import android.os.PersistableBundle;
import android.provider.Settings;
import android.view.Choreographer;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** User-started projection session; one reusable VirtualDisplay, never a cached consent token. */
public final class CaptureService extends Service {
    static final String EXTRA_RESULT_CODE = "projection_result_code";
    static final String EXTRA_RESULT_DATA = "projection_result_data";
    static final String STOP = "com.autoquestion.mobile.STOP";
    private static final int NOTIFICATION_ID = 104;
    private static final String CHANNEL = "screen-session";
    private static volatile boolean running;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService requests = Executors.newSingleThreadExecutor();
    private final AtomicBoolean busy = new AtomicBoolean(false);
    private final AtomicBoolean waitingForFrame = new AtomicBoolean(false);
    private final Object frameLock = new Object();
    private HandlerThread frameThread;
    private Handler frames;
    private WindowManager windowManager;
    private MediaProjection projection;
    private VirtualDisplay display;
    private volatile ImageReader reader;
    private BubbleView bubble;
    private LinearLayout panel;
    private Dialog panelDialog;
    private WindowManager.LayoutParams bubbleParams;
    private volatile boolean closing;
    private volatile VisionClient client;
    private List<AnswerProtocol.Result> lastResults;
    private int captureWidth, captureHeight, sourceWidth, sourceHeight;
    private boolean bubbleAttached;
    private boolean contentVisible = true;

    static boolean isRunning() { return running; }

    private final MediaProjection.Callback projectionCallback = new MediaProjection.Callback() {
        @Override public void onStop() { stopSelf(); }
        @Override public void onCapturedContentResize(int width, int height) {
            if (width > 0 && height > 0 && !closing) resizeCapture(width, height);
        }
        @Override public void onCapturedContentVisibilityChanged(boolean visible) { contentVisible = visible; }
    };

    @Override public void onCreate() {
        super.onCreate();
        windowManager = getSystemService(WindowManager.class);
        frameThread = new HandlerThread("AutoQuestion frames"); frameThread.start();
        frames = new Handler(frameThread.getLooper());
        NotificationManager notifications = getSystemService(NotificationManager.class);
        NotificationChannel channel = new NotificationChannel(CHANNEL, "悬浮识题", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("屏幕共享开启时显示，可随时停止。");
        notifications.createNotificationChannel(channel);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || STOP.equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if (projection != null) return START_NOT_STICKY;
        try {
            int code = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED);
            Intent data = Build.VERSION.SDK_INT >= 33 ? intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent.class)
                    : intent.getParcelableExtra(EXTRA_RESULT_DATA);
            if (code != Activity.RESULT_OK || data == null || !Settings.canDrawOverlays(this)) {
                throw new IllegalStateException("未授权");
            }
            // The foreground mediaProjection service must exist before getMediaProjection().
            if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIFICATION_ID, notification("轻点 AQ 读取当前题目"), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
            else startForeground(NOTIFICATION_ID, notification("轻点 AQ 读取当前题目"));
            projection = getSystemService(MediaProjectionManager.class).getMediaProjection(code, data);
            // Do not retain or reuse the one-session consent Intent.
            intent.removeExtra(EXTRA_RESULT_DATA);
            projection.registerCallback(projectionCallback, main);
            Rect bounds = screenBounds(); sourceWidth = bounds.width(); sourceHeight = bounds.height();
            setCaptureDimensions(sourceWidth, sourceHeight);
            reader = newReader();
            display = projection.createVirtualDisplay("AutoQuestion user session", captureWidth, captureHeight,
                    getResources().getConfiguration().densityDpi, DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    reader.getSurface(), null, frames);
            if (display == null) throw new IllegalStateException("无法创建屏幕共享显示");
            createBubble();
            running = true;
        } catch (Exception e) {
            Toast.makeText(this, "启动失败，请检查悬浮窗权限并重新授权屏幕共享。", Toast.LENGTH_LONG).show();
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    private Notification notification(String message) {
        PendingIntent open = PendingIntent.getActivity(this, 1, new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 2, new Intent(this, CaptureService.class).setAction(STOP),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL).setSmallIcon(com.autoquestion.mobile.R.drawable.ic_notification)
                .setContentTitle("AutoQuestion · 屏幕共享已开启").setContentText(message)
                .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_SECRET)
                .addAction(new Notification.Action.Builder(null, "停止", stop).build()).build();
    }

    private void updateNotification(String value) {
        if (!closing) getSystemService(NotificationManager.class).notify(NOTIFICATION_ID, notification(value));
    }

    private Rect screenBounds() {
        if (Build.VERSION.SDK_INT >= 30) return windowManager.getMaximumWindowMetrics().getBounds();
        android.util.DisplayMetrics metrics = new android.util.DisplayMetrics();
        windowManager.getDefaultDisplay().getRealMetrics(metrics);
        return new Rect(0, 0, metrics.widthPixels, metrics.heightPixels);
    }

    private void setCaptureDimensions(int width, int height) {
        double scale = Math.min(1.0, 2048.0 / Math.max(width, height));
        captureWidth = Math.max(1, (int) Math.round(width * scale));
        captureHeight = Math.max(1, (int) Math.round(height * scale));
    }

    private ImageReader newReader() {
        ImageReader next = ImageReader.newInstance(captureWidth, captureHeight, PixelFormat.RGBA_8888, 2);
        next.setOnImageAvailableListener(this::onImage, frames);
        return next;
    }

    private void replaceSurface(boolean armCapture) {
        synchronized (frameLock) {
            if (display == null || closing) return;
            ImageReader previous = reader;
            reader = newReader();
            if (armCapture) waitingForFrame.set(true);
            display.setSurface(reader.getSurface());
            if (previous != null) previous.close();
        }
    }

    private void resizeCapture(int width, int height) {
        if (width == sourceWidth && height == sourceHeight) return;
        sourceWidth = width; sourceHeight = height;
        setCaptureDimensions(width, height);
        if (display != null) {
            if (waitingForFrame.getAndSet(false)) finishError("屏幕方向发生变化，请再点一次 AQ。");
            display.resize(captureWidth, captureHeight, getResources().getConfiguration().densityDpi);
            replaceSurface(false);
        }
        clampBubble();
    }

    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        if (Build.VERSION.SDK_INT < 34) {
            Rect bounds = screenBounds(); resizeCapture(bounds.width(), bounds.height());
        }
        hidePanel(); clampBubble();
    }

    private void createBubble() {
        bubble = new BubbleView(this); bubble.setText(R.string.bubble_label); bubble.setTextSize(14);
        bubble.setTextColor(Color.WHITE); bubble.setTypeface(Typeface.DEFAULT, Typeface.BOLD); bubble.setGravity(Gravity.CENTER);
        bubble.setContentDescription("AutoQuestion，轻点识题，拖动移动，长按查看答案或停止");
        bubble.setBackground(background(Color.rgb(120, 96, 216), 11)); bubble.setElevation(dp(5));
        bubbleParams = overlayParams(dp(42), dp(42)); bubbleParams.x = dp(8); bubbleParams.y = dp(76);
        final int[] start = new int[2]; final float[] down = new float[2];
        final boolean[] dragged = {false}, held = {false};
        bubble.setOnClickListener(view -> requestCapture());
        bubble.setOnLongClickListener(view -> { showPanel(null); return true; });
        Runnable hold = () -> { held[0] = true; bubble.performLongClick(); };
        bubble.setOnTouchListener((view, event) -> {
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    start[0] = bubbleParams.x; start[1] = bubbleParams.y;
                    down[0] = event.getRawX(); down[1] = event.getRawY(); dragged[0] = false; held[0] = false;
                    main.postDelayed(hold, ViewConfiguration.getLongPressTimeout()); return true;
                case MotionEvent.ACTION_MOVE:
                    float dx = event.getRawX() - down[0], dy = event.getRawY() - down[1];
                    if (Math.hypot(dx, dy) > ViewConfiguration.get(this).getScaledTouchSlop()) {
                        dragged[0] = true; main.removeCallbacks(hold); hidePanel();
                        bubbleParams.x = start[0] + Math.round(dx); bubbleParams.y = start[1] + Math.round(dy); clampBubble();
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                    main.removeCallbacks(hold);
                    if (!dragged[0] && !held[0]) view.performClick();
                    return true;
                case MotionEvent.ACTION_CANCEL: main.removeCallbacks(hold); return true;
                default: return false;
            }
        });
        attachBubble();
    }

    // Drag coordinates and the user's requested top-left anchor are physical screen coordinates.
    @android.annotation.SuppressLint("RtlHardcoded")
    private WindowManager.LayoutParams overlayParams(int width, int height) {
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(width, height,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_SECURE,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.TOP | Gravity.LEFT; return params;
    }

    private void clampBubble() {
        if (bubbleParams == null) return;
        Rect bounds = screenBounds();
        bubbleParams.x = Math.max(0, Math.min(bubbleParams.x, bounds.width() - dp(42)));
        bubbleParams.y = Math.max(0, Math.min(bubbleParams.y, bounds.height() - dp(80)));
        if (bubbleAttached) {
            try { windowManager.updateViewLayout(bubble, bubbleParams); }
            catch (RuntimeException e) { stopSelf(); }
        }
    }

    private void attachBubble() {
        if (bubble == null || bubbleAttached || closing) return;
        bubble.setText(busy.get() ? "···" : "AQ");
        try { windowManager.addView(bubble, bubbleParams); bubbleAttached = true; }
        catch (RuntimeException e) { stopSelf(); }
    }

    private void detachBubble() {
        if (bubbleAttached) {
            try { windowManager.removeViewImmediate(bubble); } catch (RuntimeException ignored) { }
            bubbleAttached = false;
        }
    }

    private void requestCapture() {
        if (closing || !busy.compareAndSet(false, true)) return;
        lastResults = null;
        if (!contentVisible) { finishError("共享的应用当前不可见。请打开题目应用，或重新授权“整个屏幕”。"); return; }
        hidePanel(); detachBubble();
        updateNotification("正在读取这一屏，图片不会保存到相册");
        // Wait for compositor frames, not a guessed sleep. A fresh ImageReader surface
        // excludes queued images from before our secure overlays were removed.
        Choreographer.getInstance().postFrameCallback(frame ->
                Choreographer.getInstance().postFrameCallback(next -> {
                    if (closing) return;
                    try { replaceSurface(true); main.postDelayed(frameTimeout, 5000); }
                    catch (RuntimeException e) { finishError("屏幕共享已不可用，请停止后重新授权。"); }
                }));
    }

    private final Runnable frameTimeout = () -> {
        if (waitingForFrame.getAndSet(false)) finishError("没有收到可用的屏幕画面。受保护的应用可能禁止截屏，请切换页面后重试。");
    };

    private void onImage(ImageReader source) {
        Image image = null;
        Bitmap bitmap = null;
        try {
            synchronized (frameLock) {
                if (source != reader || closing) return;
                image = source.acquireLatestImage();
                if (image == null || !waitingForFrame.compareAndSet(true, false)) return;
                main.removeCallbacks(frameTimeout);
                bitmap = bitmapFrom(image);
                image.close(); image = null;
            }
            if (bitmap == null) { main.post(() -> finishError("画面为空或被应用保护，未发送图片。请换一个允许截屏的页面。")); return; }
            Bitmap captured = bitmap; bitmap = null;
            main.post(() -> { attachBubble(); updateNotification("正在分析题目，题多请稍等 · 长按 AQ 可停止"); });
            CaptureTask task = new CaptureTask(captured);
            try { requests.execute(task); }
            catch (java.util.concurrent.RejectedExecutionException e) { task.discard(); }
        } catch (Exception e) {
            if (!closing && busy.get()) main.post(() -> finishError("无法读取这一屏，请旋转回来或重新授权屏幕共享。"));
        } finally {
            if (image != null) image.close();
            if (bitmap != null) { bitmap.eraseColor(Color.TRANSPARENT); bitmap.recycle(); }
        }
    }

    private final class CaptureTask implements Runnable {
        private Bitmap captured;
        CaptureTask(Bitmap captured) { this.captured = captured; }
        private synchronized Bitmap take() { Bitmap bitmap = captured; captured = null; return bitmap; }
        void discard() {
            Bitmap bitmap = take();
            if (bitmap != null) { bitmap.eraseColor(Color.TRANSPARENT); bitmap.recycle(); }
        }
        @Override public void run() { Bitmap bitmap = take(); if (bitmap != null) analyze(bitmap); }
    }

    private Bitmap bitmapFrom(Image image) {
        int width = image.getWidth(), height = image.getHeight();
        Image.Plane plane = image.getPlanes()[0]; ByteBuffer buffer = plane.getBuffer();
        int row = plane.getRowStride(), pixel = plane.getPixelStride();
        if (pixel < 4 || width <= 0 || height <= 0 || (long) width * height > 4194304L) return null;
        int[] colors = new int[width * height];
        boolean nonBlack = false;
        try {
            for (int y = 0; y < height; y++) {
                for (int x = 0; x < width; x++) {
                    int offset = y * row + x * pixel;
                    int r = buffer.get(offset) & 255, g = buffer.get(offset + 1) & 255, b = buffer.get(offset + 2) & 255;
                    colors[y * width + x] = Color.rgb(r, g, b);
                    if (x % 16 == 0 && y % 16 == 0 && (r > 20 || g > 20 || b > 20)) nonBlack = true;
                }
            }
            if (!nonBlack) return null;
            // createBitmap(int[]) is immutable on Android; our cleanup must be able
            // to erase pixels before recycle on success, cancellation, and failure.
            Bitmap captured = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            captured.setPixels(colors, 0, width, 0, 0, width, height);
            return captured;
        } finally { Arrays.fill(colors, 0); }
    }

    private void analyze(Bitmap bitmap) {
        byte[] png = null;
        VisionClient request = new VisionClient();
        try {
            if (closing) return;
            try (ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, output);
                png = output.toByteArray();
            }
            bitmap.eraseColor(Color.TRANSPARENT); bitmap.recycle();
            if (closing) return;
            if (png.length > 12582912) throw new VisionClient.Failure("画面太大，请减少屏幕内容后重试。");
            SecureStore secure = new SecureStore(this); ApiConfig config = secure.config();
            client = request;
            if (closing) { request.cancel(); return; }
            List<AnswerProtocol.Result> results = request.analyze(config, secure.readKey(config), png);
            main.post(() -> {
                if (closing) return;
                lastResults = results; busy.set(false); attachBubble(); bubble.setText(R.string.bubble_label);
                updateNotification("已完成 " + results.size() + " 题 · 轻点 AQ 读取下一屏"); hidePanel(); showPanel(null);
            });
        } catch (VisionClient.Failure e) { main.post(() -> finishError(e.getMessage()));
        } catch (Exception e) { main.post(() -> finishError("无法读取安全保存的 API Key，请回主界面重新保存配置。"));
        } finally {
            if (!bitmap.isRecycled()) { bitmap.eraseColor(Color.TRANSPARENT); bitmap.recycle(); }
            if (png != null) Arrays.fill(png, (byte) 0);
            if (client == request) client = null;
        }
    }

    private void finishError(String error) {
        if (closing) return;
        waitingForFrame.set(false); main.removeCallbacks(frameTimeout); busy.set(false);
        attachBubble(); if (bubble != null) bubble.setText(R.string.bubble_label);
        lastResults = null;
        updateNotification("本次未完成 · 轻点 AQ 可重试"); hidePanel(); showPanel(error);
    }

    private void showPanel(String error) {
        if (closing || panel != null) return;
        panel = new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16), dp(14), dp(16), dp(14));
        panel.setBackground(background(Color.WHITE, 17)); panel.setElevation(dp(8));
        TextView title = label(error != null ? "这次没有完成" : busy.get() ? "正在分析这一屏…" : "AutoQuestion · 本屏答案", 16, true);
        panel.addView(title);
        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(body);
        int maxBody = Math.min(dp(320), (int) (screenBounds().height() * .42));
        LinearLayout.LayoutParams scrollParams = new LinearLayout.LayoutParams(-1,
                error == null && lastResults != null ? maxBody : -2); scrollParams.topMargin = dp(10);
        panel.addView(scroll, scrollParams);
        if (error != null) body.addView(label(error, 14, false));
        else if (busy.get()) body.addView(label("正在分别分析这一屏的题目，题多时可能需要更久。最长等待约 3 分钟，可收起面板继续查看，或随时停止共享。", 14, false));
        else if (lastResults == null) body.addView(label("轻点小方框，识别当前屏幕的完整题目。", 14, false));
        else for (int i = 0; i < lastResults.size(); i++) {
            AnswerProtocol.Result result = lastResults.get(i);
            TextView number = label("第 " + (i + 1) + " 题 · " + result.typeLabel(), 12, true);
            number.setTextColor(Color.rgb(120, 96, 216)); number.setPadding(0, i == 0 ? 0 : dp(20), 0, dp(5)); body.addView(number);
            body.addView(label(result.question, 14, false));
            if (result.blankAnswers.isEmpty()) {
                body.addView(label("答案", 12, true));
                body.addView(selectableAnswer(result.answer, "第 " + (i + 1) + " 题答案"));
            } else for (int blank = 0; blank < result.blankAnswers.size(); blank++) {
                body.addView(label("第 " + (blank + 1) + " 空", 12, true));
                String value = result.blankAnswers.get(blank);
                body.addView(selectableAnswer(value, "第 " + (i + 1) + " 题第 " + (blank + 1) + " 空答案"));
                Button copyBlank = panelButton("复制第 " + (blank + 1) + " 空", () -> copyAnswer(value));
                copyBlank.setContentDescription("复制第 " + (i + 1) + " 题第 " + (blank + 1) + " 空");
                body.addView(copyBlank, new LinearLayout.LayoutParams(-1, dp(44)));
            }
            Button copy = panelButton("复制本题答案", () -> copyAnswer(result.answer));
            copy.setContentDescription("复制第 " + (i + 1) + " 题完整答案");
            body.addView(copy, new LinearLayout.LayoutParams(-1, dp(44)));
            body.addView(label(result.reason + "  ·  " + Math.round(result.confidence * 100) + "%", 12, false));
        }
        TextView hint = label("长按答案可选择文字；复制后请自行切换应用粘贴。不会自动填写或提交。", 11, false); hint.setPadding(0, dp(10), 0, dp(2)); panel.addView(hint);
        LinearLayout actions = new LinearLayout(this); actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.addView(panelButton("收起", this::hidePanel), new LinearLayout.LayoutParams(0, dp(44), 1));
        actions.addView(panelButton("停止", this::stopSelf), new LinearLayout.LayoutParams(0, dp(44), 1));
        panel.addView(actions);
        int width = Math.min(dp(330), screenBounds().width() - dp(24));
        WindowManager.LayoutParams params = overlayParams(width, -2);
        // A Dialog's DecorView hosts native selection ActionMode and handles.
        // A raw WindowManager root cannot host ActionMode, even when focusable.
        params.flags &= ~WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;
        params.flags |= WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL | WindowManager.LayoutParams.FLAG_ALT_FOCUSABLE_IM
                | WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH;
        params.x = Math.max(dp(8), Math.min(bubbleParams.x, screenBounds().width() - width - dp(8)));
        params.y = Math.max(dp(20), Math.min(bubbleParams.y + dp(50), screenBounds().height() - dp(500)));
        try {
            Dialog dialog = new Dialog(this, android.R.style.Theme_Material_Light_Dialog_NoActionBar);
            dialog.setContentView(panel);
            dialog.setCanceledOnTouchOutside(true);
            android.view.Window window = dialog.getWindow();
            if (window == null) throw new IllegalStateException("无答案窗口");
            window.setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(Color.TRANSPARENT));
            window.setAttributes(params);
            dialog.setOnDismissListener(ignored -> {
                if (panelDialog == dialog) {
                    panelDialog = null;
                    if (panel != null) panel.removeAllViews();
                    panel = null;
                }
            });
            panelDialog = dialog;
            dialog.show();
            window.getDecorView().setPadding(0, 0, 0, 0);
            window.setLayout(width, WindowManager.LayoutParams.WRAP_CONTENT);
        } catch (RuntimeException e) { hidePanel(); stopSelf(); }
    }

    private TextView selectableAnswer(String value, String description) {
        TextView view = new AnswerTextView(this);
        view.setText(value); view.setTextSize(17); view.setTextColor(Color.rgb(42, 38, 58));
        view.setLineSpacing(dp(3), 1); view.setPadding(0, dp(9), 0, dp(7));
        view.setContentDescription(description); return view;
    }

    /** Only explicit button/context-menu actions call this; the app never reads the clipboard. */
    private void copyAnswer(String value) {
        if (closing) return;
        try {
            ClipData clip = ClipData.newPlainText("AutoQuestion 答案", value);
            if (Build.VERSION.SDK_INT >= 33) {
                PersistableBundle extras = new PersistableBundle();
                extras.putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true);
                clip.getDescription().setExtras(extras);
            }
            getSystemService(ClipboardManager.class).setPrimaryClip(clip);
            if (Build.VERSION.SDK_INT < 33) Toast.makeText(this, "已复制，可自行切换应用粘贴。", Toast.LENGTH_SHORT).show();
        } catch (RuntimeException error) {
            Toast.makeText(this, "未能复制，请长按选择答案后重试。", Toast.LENGTH_SHORT).show();
        }
    }

    private final class AnswerTextView extends TextView {
        AnswerTextView(android.content.Context context) {
            super(context);
            setTextIsSelectable(true);
            setCustomSelectionActionModeCallback(new android.view.ActionMode.Callback() {
                @Override public boolean onCreateActionMode(android.view.ActionMode mode, android.view.Menu menu) { return true; }
                @Override public boolean onPrepareActionMode(android.view.ActionMode mode, android.view.Menu menu) {
                    for (int i = menu.size() - 1; i >= 0; i--) {
                        int id = menu.getItem(i).getItemId();
                        if (id != android.R.id.copy && id != android.R.id.selectAll) menu.removeItem(id);
                    }
                    return true;
                }
                @Override public boolean onActionItemClicked(android.view.ActionMode mode, android.view.MenuItem item) { return false; }
                @Override public void onDestroyActionMode(android.view.ActionMode mode) { }
            });
        }
        @Override public boolean onTextContextMenuItem(int id) {
            if (id == android.R.id.copy) {
                int from = Math.min(getSelectionStart(), getSelectionEnd());
                int to = Math.max(getSelectionStart(), getSelectionEnd());
                if (from >= 0 && to > from && to <= length()) copyAnswer(getText().subSequence(from, to).toString());
                return true;
            }
            return super.onTextContextMenuItem(id);
        }
    }

    private void hidePanel() {
        Dialog previous = panelDialog; panelDialog = null;
        LinearLayout previousPanel = panel; panel = null;
        if (previous != null) { try { previous.dismiss(); } catch (RuntimeException ignored) { } }
        if (previousPanel != null) previousPanel.removeAllViews();
    }

    private TextView label(String value, int size, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size);
        view.setTextColor(Color.rgb(42, 38, 58)); view.setLineSpacing(dp(3), 1);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return view;
    }
    private static final class BubbleView extends TextView {
        BubbleView(android.content.Context context) { super(context); }
        @Override public boolean performClick() { return super.performClick(); }
    }
    private Button panelButton(String value, Runnable action) {
        Button button = new Button(this); button.setText(value); button.setTextSize(13); button.setAllCaps(false);
        button.setTextColor(Color.rgb(120, 96, 216)); button.setBackgroundColor(Color.TRANSPARENT);
        button.setOnClickListener(v -> action.run()); return button;
    }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable background = new GradientDrawable(); background.setColor(color); background.setCornerRadius(dp(radius)); return background;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    @Override public void onTaskRemoved(Intent rootIntent) { stopSelf(); super.onTaskRemoved(rootIntent); }

    @Override public void onDestroy() {
        closing = true; running = false; waitingForFrame.set(false);
        main.removeCallbacksAndMessages(null); hidePanel(); detachBubble();
        VisionClient request = client; if (request != null) request.cancel();
        for (Runnable queued : requests.shutdownNow()) if (queued instanceof CaptureTask) ((CaptureTask) queued).discard();
        synchronized (frameLock) {
            if (display != null) { display.release(); display = null; }
            if (reader != null) { reader.close(); reader = null; }
        }
        if (projection != null) {
            projection.unregisterCallback(projectionCallback); projection.stop(); projection = null;
        }
        if (frameThread != null) frameThread.quitSafely();
        lastResults = null; bubble = null;
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
