package com.autoquestion.mobile;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.projection.MediaProjectionConfig;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** One local setup screen. Home keeps the user-started overlay; Exit ends it. */
public final class MainActivity extends Activity {
    private static final int CAPTURE_REQUEST = 31, NOTIFICATION_REQUEST = 32;
    private static final int INK = Color.rgb(32, 30, 48), MUTED = Color.rgb(112, 107, 133);
    private static final int PURPLE = Color.rgb(120, 96, 216), BACKGROUND = Color.rgb(246, 245, 251);
    private SecureStore store;
    private EditText url, model, key;
    private TextView status;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        store = new SecureStore(this);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BACKGROUND);
        LinearLayout page = column(24);
        scroll.addView(page);
        page.setOnApplyWindowInsetsListener((view, insets) -> {
            int top, bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(android.view.WindowInsets.Type.systemBars());
                top = bars.top;
                bottom = Math.max(bars.bottom, insets.getInsets(android.view.WindowInsets.Type.ime()).bottom);
            } else {
                top = insets.getSystemWindowInsetTop(); bottom = insets.getSystemWindowInsetBottom();
            }
            view.setPadding(dp(24), dp(22) + top, dp(24), dp(24) + bottom);
            return insets;
        });
        setContentView(scroll);
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    () -> { stopService(new Intent(this, CaptureService.class)); finish(); });
        }

        TextView mark = text("A·  AutoQuestion", 26, INK, true);
        page.addView(mark);
        addText(page, "手机上的屏幕答题助手", 15, MUTED, false, 8);
        addText(page, "题目在屏幕上，轻点一下。", 28, INK, true, 30);
        addText(page, "单选、多选、判断、填空和简答/解答，同屏多道分别回答。\n用你自己的模型和 API Key。", 15, MUTED, false, 10);

        LinearLayout config = card(page, 24);
        addText(config, "01  配置图片模型", 18, INK, true, 0);
        addText(config, "点一个示例填入 URL 和 model，再填写自己的 Key。", 13, MUTED, false, 8);
        LinearLayout examples = new LinearLayout(this);
        examples.setOrientation(LinearLayout.HORIZONTAL);
        config.addView(examples);
        Button deepseek = smallButton("DeepSeek", () -> preset("https://api.deepseek.com", "deepseek-flash"));
        Button openai = smallButton("OpenAI", () -> preset("https://api.openai.com/v1", "gpt-4.1-mini"));
        examples.addView(deepseek, new LinearLayout.LayoutParams(0, dp(48), 1));
        LinearLayout.LayoutParams chip = new LinearLayout.LayoutParams(0, dp(48), 1); chip.leftMargin = dp(8);
        examples.addView(openai, chip);

        ApiConfig existing = store.config();
        url = field(config, "Base URL", "https://api.deepseek.com", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        url.setText(existing.baseUrl);
        model = field(config, "Model", "deepseek-flash", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        model.setText(existing.model);
        key = field(config, "API Key", store.hasKey() ? "已安全保存；留空保留" : "填写你在服务商申请的 API Key",
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        key.setSaveEnabled(false);
        key.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        addText(config, "DeepSeek 示例：deepseek-flash 支持图片。deepseek-v4-pro 是文本模型，不适合手机截屏识题。"
                + "\nOpenAI 示例：gpt-4.1-mini。其他服务请填写支持 image_url 的 model ID。", 12, MUTED, false, 12);
        config.addView(button("保存配置", false, this::saveSettings));
        TextView forget = text("清除已保存的 API Key", 13, PURPLE, false);
        forget.setPadding(0, dp(12), 0, dp(4));
        forget.setOnClickListener(v -> new AlertDialog.Builder(this).setTitle("清除 API Key？")
                .setMessage("同时停止悬浮识题。URL 和 model 会保留。")
                .setNegativeButton("取消", null).setPositiveButton("清除", (dialog, which) -> {
                    stopService(new Intent(this, CaptureService.class));
                    try { store.forget(); key.setText(""); key.setHint("请重新填写 API Key"); setStatus("API Key 已清除，服务已停止。"); }
                    catch (Exception e) { setStatus("清除失败，请重试。"); }
                }).show());
        config.addView(forget);

        LinearLayout launch = card(page, 18);
        addText(launch, "02  开启小悬浮按钮", 18, INK, true, 0);
        addText(launch, "授权显示在其他应用上层和屏幕共享。需要切换多个应用时，请在系统弹窗选择“整个屏幕”。", 14, MUTED, false, 10);
        launch.addView(button("开启悬浮识题  ↗", true, this::startFlow));
        launch.addView(button("停止并退出", false, () -> {
            stopService(new Intent(this, CaptureService.class));
            finishAndRemoveTask();
        }));
        status = text("", 13, PURPLE, false);
        status.setPadding(0, dp(12), 0, 0);
        launch.addView(status);

        LinearLayout tips = card(page, 18);
        addText(tips, "小方框，三个动作", 18, INK, true, 0);
        addText(tips, "轻点 AQ  ·  识别当前屏幕全部完整题目\n拖动方框  ·  移动到不挡题的位置\n长按方框  ·  查看上次答案或停止", 14, MUTED, false, 12);
        addText(tips, "答案可长按选择或点按钮复制，填空支持逐空复制。复制后请自行切换应用粘贴。"
                + "\n按 Home 后可继续悬浮。点“停止并退出”、划除最近任务或在通知里停止，都会释放屏幕共享和悬浮窗。锁屏或系统结束共享后，需要重新开启。", 12, MUTED, false, 12);

        addText(page, "只在你轻点时发送一张屏幕图片给所填 API。\n图片只在内存中处理，不写相册、文件或历史；答案也只在当前会话保留。"
                + "\n主动复制后，系统剪贴板可能在停止应用后继续保留答案。应用不会自动读取或清空剪贴板。"
                + "\n没有服务器，没有遥测，不会点击或提交答案。\n受保护或禁止截屏的应用可能无法识别。", 12, MUTED, false, 24);
        addText(page, "AutoQuestion 0.4.0  ·  Android 8+", 12, MUTED, false, 18);
        TextView license = text("Apache License 2.0", 12, PURPLE, false);
        license.setPadding(0, dp(8), 0, dp(8));
        license.setOnClickListener(view -> {
            try (java.io.InputStream input = getAssets().open("LICENSE");
                    java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096]; int read;
                while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
                new AlertDialog.Builder(this).setTitle("Apache License 2.0")
                        .setMessage(output.toString(java.nio.charset.StandardCharsets.UTF_8.name()))
                        .setPositiveButton("关闭", null).show();
            } catch (java.io.IOException error) { setStatus("许可证见项目 GitHub 根目录 LICENSE。"); }
        });
        page.addView(license);
        updateStatus();
    }

    @Override protected void onResume() { super.onResume(); if (status != null) updateStatus(); }

    private void updateStatus() {
        if (CaptureService.isRunning()) setStatus("悬浮识题已开启 · 轻点左上角 AQ 开始");
        else setStatus(store.hasKey() ? "配置已保存。点上方按钮开启悬浮识题。" : "先保存配置，再开启悬浮识题。");
    }

    private boolean saveSettings() {
        if (CaptureService.isRunning()) { setStatus("请先停止悬浮识题，再修改配置。"); return false; }
        try {
            ApiConfig config = new ApiConfig(url.getText().toString(), model.getText().toString());
            String supplied = key.getText().toString();
            store.save(config, supplied);
            key.setText(""); key.setHint("已安全保存；留空保留");
            setStatus("已安全保存。屏幕图片将发送至 " + config.host() + "。");
            return true;
        } catch (IllegalArgumentException e) { setStatus(e.getMessage()); return false;
        } catch (Exception e) { setStatus("无法安全保存 Key，请检查设备锁屏设置后重试。"); return false; }
    }

    private void startFlow() {
        if (CaptureService.isRunning()) { setStatus("悬浮识题已经开启，无需重复启动。"); moveTaskToBack(true); return; }
        if (!saveSettings()) return;
        if (!Settings.canDrawOverlays(this)) {
            setStatus("请允许“显示在其他应用上层”，返回后再次点击开启。");
            try { startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()))); }
            catch (Exception e) { setStatus("请到系统设置 → 应用 → AutoQuestion，允许悬浮窗后再试。"); }
            return;
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                && !getPreferences(MODE_PRIVATE).getBoolean("asked_notifications", false)) {
            getPreferences(MODE_PRIVATE).edit().putBoolean("asked_notifications", true).apply();
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_REQUEST);
        } else requestCapture();
    }

    private void requestCapture() {
        MediaProjectionManager manager = getSystemService(MediaProjectionManager.class);
        try {
            Intent request = Build.VERSION.SDK_INT >= 34
                    ? manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
                    : manager.createScreenCaptureIntent();
            startActivityForResult(request, CAPTURE_REQUEST);
        } catch (Exception e) { setStatus("无法打开系统屏幕共享授权，请重新打开应用再试。"); }
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == NOTIFICATION_REQUEST) requestCapture();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != CAPTURE_REQUEST) return;
        if (resultCode != RESULT_OK || data == null) { setStatus("未授权屏幕共享，未启动识题。"); return; }
        Intent service = new Intent(this, CaptureService.class)
                .putExtra(CaptureService.EXTRA_RESULT_CODE, resultCode)
                .putExtra(CaptureService.EXTRA_RESULT_DATA, data);
        try { startForegroundService(service); moveTaskToBack(true); }
        catch (Exception e) { setStatus("启动失败。请检查悬浮窗权限，再次授权屏幕共享。"); }
    }

    // API 33+ uses the registered OnBackInvokedDispatcher; this is the API 26-32 path.
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed() {
        stopService(new Intent(this, CaptureService.class));
        super.onBackPressed();
    }

    private void preset(String endpoint, String name) {
        if (CaptureService.isRunning()) { setStatus("请先停止悬浮识题，再修改配置。"); return; }
        url.setText(endpoint); model.setText(name);
        setStatus("示例已填入，请使用对应服务商的 API Key。");
    }

    private void setStatus(String value) { if (status != null) status.setText(value); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private LinearLayout column(int padding) {
        LinearLayout layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(padding), dp(padding), dp(padding), dp(padding)); return layout;
    }
    private LinearLayout card(LinearLayout parent, int top) {
        LinearLayout view = column(20);
        GradientDrawable background = new GradientDrawable(); background.setColor(Color.WHITE); background.setCornerRadius(dp(20));
        view.setBackground(background);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(top);
        parent.addView(view, params); return view;
    }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setLineSpacing(dp(3), 1); if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return view;
    }
    private void addText(LinearLayout parent, String value, int size, int color, boolean bold, int top) {
        TextView view = text(value, size, color, bold);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(top);
        parent.addView(view, params);
    }
    private EditText field(LinearLayout parent, String label, String hint, int type) {
        addText(parent, label, 13, INK, true, 16);
        EditText field = new EditText(this); field.setSingleLine(true); field.setInputType(type);
        field.setTextSize(15); field.setTextColor(INK); field.setHintTextColor(MUTED); field.setHint(hint);
        field.setPadding(dp(12), dp(10), dp(12), dp(10));
        GradientDrawable background = new GradientDrawable(); background.setColor(BACKGROUND); background.setCornerRadius(dp(10));
        background.setStroke(dp(1), Color.rgb(231, 227, 242)); field.setBackground(background);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(48)); params.topMargin = dp(6);
        parent.addView(field, params); return field;
    }
    private Button button(String label, boolean primary, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setAllCaps(false); button.setTextSize(15);
        button.setTextColor(primary ? Color.WHITE : PURPLE); button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        GradientDrawable background = new GradientDrawable(); background.setColor(primary ? PURPLE : Color.rgb(241, 237, 251));
        background.setCornerRadius(dp(12)); button.setBackground(background);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(50)); params.topMargin = dp(14);
        button.setLayoutParams(params); button.setOnClickListener(v -> action.run()); return button;
    }
    private Button smallButton(String label, Runnable action) {
        Button button = button(label, false, action); button.setTextSize(13); button.setPadding(0, 0, 0, 0);
        return button;
    }
}
