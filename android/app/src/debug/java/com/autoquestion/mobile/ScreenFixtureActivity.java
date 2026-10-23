package com.autoquestion.mobile;

import android.app.Activity;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CountDownLatch;

/** Debug-only public practice screen. This class and its manifest entry never enter a release APK. */
@SuppressWarnings("deprecation")
@android.annotation.SuppressLint("SetTextI18n") // Literal practice data belongs only to the debug fixture.
public final class ScreenFixtureActivity extends Activity {
    private static final Set<ScreenFixtureActivity> ownedActivities = new HashSet<>();
    final CountDownLatch frameCommitted = new CountDownLatch(1);
    EditText pasteTarget;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ownedActivities.add(this);
        getWindow().setWindowAnimations(0);
        overridePendingTransition(0, 0);
        FrameLayout page = new FrameLayout(this);
        page.setBackgroundColor(Color.CYAN);
        TextView fixture = new TextView(this);
        fixture.setTextColor(Color.BLACK); fixture.setBackgroundColor(Color.CYAN); fixture.setTextSize(15);
        fixture.setPadding(8, 40, 8, 8);
        fixture.setText("Synthetic questions — no private screen\n\n1. Single: Alpha?\nA Alpha   B Beta\n\n"
                + "2. Multiple: Alpha and Gamma?\nA Alpha   B Beta   C Gamma\n\n"
                + "3. True/False: one equals one?\nTrue   False\n\n"
                + "4. Fill: one plus one = __; speed formula = __\n\n"
                + "5. Short: solve x+y=5 and x-y=1.\n\n"
                + "6. Short: explain photosynthesis in two paragraphs.");
        page.addView(fixture, new FrameLayout.LayoutParams(-1, -1));
        pasteTarget = new EditText(this); pasteTarget.setSingleLine(false);
        pasteTarget.setTextColor(Color.BLACK); pasteTarget.setBackgroundColor(Color.CYAN);
        pasteTarget.setHint("Synthetic paste target"); pasteTarget.setSaveEnabled(false);
        page.addView(pasteTarget, new FrameLayout.LayoutParams(-1, 72, Gravity.BOTTOM));
        page.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener() {
            @Override public void onViewAttachedToWindow(View view) {
                if (Build.VERSION.SDK_INT >= 29) {
                    view.getViewTreeObserver().registerFrameCommitCallback(frameCommitted::countDown);
                } else view.postOnAnimation(() -> view.postOnAnimation(frameCommitted::countDown));
                view.invalidate();
            }
            @Override public void onViewDetachedFromWindow(View view) { }
        });
        setContentView(page);
    }

    @Override protected void onDestroy() {
        ownedActivities.remove(this);
        super.onDestroy();
    }

    static void finishOwnedActivities() {
        for (ScreenFixtureActivity fixture : new ArrayList<>(ownedActivities)) fixture.finish();
    }
}
