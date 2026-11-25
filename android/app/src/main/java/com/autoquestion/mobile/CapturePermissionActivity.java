package com.autoquestion.mobile;

import android.app.Activity;
import android.content.Intent;
import android.media.projection.MediaProjectionConfig;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.os.ResultReceiver;

/** Hosts system consent over the question app and returns the one-use result to the overlay. */
public final class CapturePermissionActivity extends Activity {
    static final String EXTRA_RECEIVER = "capture_permission_receiver";
    static final String EXTRA_CONSENT = "capture_permission_data";
    static final int DIALOG_LAUNCHED = RESULT_FIRST_USER;
    static final int LAUNCH_FAILED = RESULT_FIRST_USER + 1;
    private static final int CAPTURE_REQUEST = 31;
    private ResultReceiver receiver;
    private int consentCode = RESULT_CANCELED;
    private Intent consentData;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        receiver = Build.VERSION.SDK_INT >= 33 ? getIntent().getParcelableExtra(EXTRA_RECEIVER, ResultReceiver.class)
                : getIntent().getParcelableExtra(EXTRA_RECEIVER);
        if (receiver == null) { finish(); return; }
        if (state != null) return;
        try {
            MediaProjectionManager manager = getSystemService(MediaProjectionManager.class);
            Intent request = Build.VERSION.SDK_INT >= 34
                    ? manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
                    : manager.createScreenCaptureIntent();
            startActivityForResult(request, CAPTURE_REQUEST);
            receiver.send(DIALOG_LAUNCHED, null);
        } catch (RuntimeException error) { complete(LAUNCH_FAILED, null); }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == CAPTURE_REQUEST) complete(resultCode, data);
    }

    private void complete(int resultCode, Intent data) {
        consentCode = resultCode;
        consentData = data;
        finish();
    }

    @Override protected void onDestroy() {
        if (isFinishing() && receiver != null) {
            // Return after the relay is dismissed so the first frame comes from the question app.
            Bundle consent = new Bundle();
            consent.putParcelable(EXTRA_CONSENT, consentData);
            receiver.send(consentCode, consent);
        }
        super.onDestroy();
    }
}
