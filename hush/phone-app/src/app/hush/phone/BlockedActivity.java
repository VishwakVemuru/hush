package app.hush.phone;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** The calm "this can wait" screen shown after a blocked app is sent home. */
public class BlockedActivity extends Activity {
    private final Handler h = new Handler(Looper.getMainLooper());
    private TextView left;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(Color.parseColor("#F3EFE7"));
        getWindow().getDecorView().setSystemUiVisibility(android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.CENTER);
        col.setBackgroundColor(Color.parseColor("#F3EFE7"));
        int pad = dp(32);
        col.setPadding(pad, pad, pad, pad);

        TextView logo = text("hush.", 44, "#1D2A3A");
        logo.setTypeface(Typeface.create(Typeface.SERIF, Typeface.ITALIC));
        col.addView(logo);

        String app = getIntent().getStringExtra("app");
        TextView t = text((app == null ? "This" : app) + " can wait.", 24, "#1D2A3A");
        t.setPadding(0, dp(24), 0, dp(8));
        col.addView(t);

        left = text("", 16, "#6B7280");
        col.addView(left);

        TextView note = text("Your laptop is in a focus session. WhatsApp, Telegram and Discord still work.", 14, "#6B7280");
        note.setPadding(0, dp(20), 0, dp(28));
        col.addView(note);

        Button ok = new Button(this);
        ok.setText("Back to focus");
        ok.setAllCaps(false);
        ok.setOnClickListener(v -> goHome());
        col.addView(ok);

        setContentView(col);
        tick.run();
    }

    private final Runnable tick = new Runnable() {
        public void run() {
            long ms = Link.blockUntil(BlockedActivity.this) - System.currentTimeMillis();
            if (ms <= 0) {
                left.setText("Focus is over. Enjoy.");
                return;
            }
            long m = (ms + 59999) / 60000;
            left.setText(m + " min of focus left");
            h.postDelayed(this, 5000);
        }
    };

    private void goHome() {
        startActivity(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }

    @Override
    public void onBackPressed() {
        goHome();
    }

    @Override
    protected void onDestroy() {
        h.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private TextView text(String s, int sp, String color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(Color.parseColor(color));
        t.setGravity(Gravity.CENTER);
        return t;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
