package app.hush.phone;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class MainActivity extends Activity {
    private static final String NAVY = "#1D2A3A", MUTED = "#6B7280", BG = "#F3EFE7", CARD = "#FFFFFF", MOSS = "#5E7D5A";
    private final Handler h = new Handler(Looper.getMainLooper());
    private TextView status, a11yText;
    private Button a11yBtn;
    private EditText codeIn;
    private LinearLayout appList;
    private final List<CheckBox> boxes = new ArrayList<>();

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(Color.parseColor(BG));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Color.parseColor(BG));
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(20), dp(28), dp(20), dp(40));
        sv.addView(col);

        TextView logo = text("hush.", 40, NAVY);
        logo.setTypeface(Typeface.create(Typeface.SERIF, Typeface.ITALIC));
        col.addView(logo);
        TextView sub = text("Your phone follows your laptop's focus sessions.", 15, MUTED);
        sub.setPadding(0, 0, 0, dp(16));
        col.addView(sub);

        // status
        LinearLayout st = card(col);
        status = text("…", 17, NAVY);
        st.addView(status);

        // step 1: pairing
        LinearLayout pair = card(col);
        pair.addView(title("1 · Pair with your laptop"));
        pair.addView(text("In hush. on your laptop, open Settings → Phone and type the 8-digit code here. Both need to be on the same Wi-Fi.", 14, MUTED));
        codeIn = new EditText(this);
        codeIn.setInputType(InputType.TYPE_CLASS_NUMBER);
        codeIn.setHint("Pairing code");
        codeIn.setTextSize(22);
        codeIn.setText(Link.prefs(this).getString("code", ""));
        pair.addView(codeIn);
        Button connect = button("Connect");
        connect.setOnClickListener(v -> connect());
        pair.addView(connect);

        // step 2: accessibility
        LinearLayout acc = card(col);
        acc.addView(title("2 · Turn on blocking"));
        a11yText = text("", 14, MUTED);
        acc.addView(a11yText);
        a11yBtn = button("Open accessibility settings");
        a11yBtn.setOnClickListener(v -> {
            try {
                startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
            } catch (Exception e) {
                startActivity(new Intent(Settings.ACTION_SETTINGS));
            }
        });
        acc.addView(a11yBtn);
        Button info = button("App info (for \"Allow restricted settings\")");
        info.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                android.net.Uri.parse("package:" + getPackageName()))));
        acc.addView(info);

        // step 3: apps
        LinearLayout apps = card(col);
        apps.addView(title("3 · Apps to block during focus"));
        apps.addView(text("WhatsApp, Telegram and Discord are never blocked. While a session is running you can add apps but not remove them.", 14, MUTED));
        appList = new LinearLayout(this);
        appList.setOrientation(LinearLayout.VERTICAL);
        apps.addView(appList);

        setContentView(sv);
        buildAppList();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh.run();
    }

    @Override
    protected void onPause() {
        h.removeCallbacks(refresh);
        super.onPause();
    }

    private final Runnable refresh = new Runnable() {
        public void run() {
            updateStatus();
            h.postDelayed(this, 2000);
        }
    };

    private boolean a11yOn() {
        String s = Settings.Secure.getString(getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        return s != null && s.contains(getPackageName() + "/");
    }

    private void updateStatus() {
        SharedPreferences p = Link.prefs(this);
        boolean enabled = a11yOn();
        boolean stalled = enabled && !BlockService.running;  // switched on, but the phone stopped it
        boolean on = enabled && BlockService.running;
        a11yText.setText(on
                ? "Blocking is on. You can close this app; blocking keeps running."
                : stalled
                ? "Your phone stopped the blocker. In accessibility settings, turn hush. off and on again. To stop it happening: Settings → Apps → hush. → Autostart on, and Battery saver → No restrictions."
                : "Find \"hush.\" under Downloaded apps (or Installed services) and turn it on. If it's greyed out: App info → ⋮ → Allow restricted settings, then try again.");
        a11yBtn.setVisibility(on ? View.GONE : View.VISIBLE);
        String code = p.getString("code", "");
        long now = System.currentTimeMillis(), until = Link.blockUntil(this), lastOk = p.getLong("lastOk", 0);
        int s = p.getInt("status", -1);
        String msg;
        String color = NAVY;
        if (code.isEmpty()) msg = "Not paired yet.";
        else if (stalled) msg = "Blocker stopped by the phone. See step 2.";
        else if (!on) msg = "Paired. Turn on blocking below.";
        else if (until > now) {
            long m = (until - now + 59999) / 60000;
            String label = p.getString("label", "");
            msg = "In focus" + (label.isEmpty() ? "" : " · " + label) + " · " + m + " min left";
            if (now - lastOk > 20000) msg += "\n(laptop out of reach, still blocking)";
            color = MOSS;
        } else if (s == Link.WRONG_CODE) msg = "Wrong code. Check Settings → Phone on the laptop.";
        else if (now - lastOk < 20000) msg = "Connected. Waiting for the laptop to start focus.";
        else msg = "Looking for your laptop… Is hush. open and on the same Wi-Fi?";
        status.setText(msg);
        status.setTextColor(Color.parseColor(color));
        boolean locked = until > now;
        Set<String> sel = Link.blocked(this);
        for (CheckBox cb : boxes) cb.setEnabled(!(locked && sel.contains((String) cb.getTag())));
    }

    private void connect() {
        final String code = codeIn.getText().toString().replaceAll("\\D", "");
        if (code.length() != 8) {
            Toast.makeText(this, "The code has 8 digits", Toast.LENGTH_SHORT).show();
            return;
        }
        Link.prefs(this).edit().putString("code", code).putString("laptopId", "").putInt("fails", 99).apply();
        status.setText("Looking for your laptop…");
        new Thread(() -> {
            final int r = Link.poll(MainActivity.this);
            h.post(() -> {
                Toast.makeText(MainActivity.this, r == Link.OK ? "Paired with your laptop" : r == Link.WRONG_CODE
                        ? "Laptop found, but the code is wrong" : "Couldn't find hush. on this Wi-Fi", Toast.LENGTH_LONG).show();
                updateStatus();
            });
        }).start();
    }

    private void buildAppList() {
        PackageManager pm = getPackageManager();
        Intent i = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> all = pm.queryIntentActivities(i, 0);
        Set<String> homes = new HashSet<>();
        for (ResolveInfo r : pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME), 0))
            homes.add(r.activityInfo.packageName);
        final Set<String> sel = Link.blocked(this);
        List<String[]> rows = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (ResolveInfo r : all) {
            String pkg = r.activityInfo.packageName;
            if (!seen.add(pkg) || pkg.equals(getPackageName()) || homes.contains(pkg)) continue;
            rows.add(new String[]{r.loadLabel(pm).toString(), pkg});
        }
        Collections.sort(rows, (a, c) -> {
            int ra = rank(a[1], sel), rc = rank(c[1], sel);
            return ra != rc ? ra - rc : a[0].compareToIgnoreCase(c[0]);
        });
        for (String[] row : rows) {
            final String pkg = row[1];
            LinearLayout line = new LinearLayout(this);
            line.setGravity(Gravity.CENTER_VERTICAL);
            line.setPadding(0, dp(6), 0, dp(6));
            ImageView icon = new ImageView(this);
            try {
                Drawable d = pm.getApplicationIcon(pkg);
                icon.setImageDrawable(d);
            } catch (Exception ignored) {
            }
            line.addView(icon, new LinearLayout.LayoutParams(dp(32), dp(32)));
            boolean allowed = Link.ALWAYS_ALLOWED.contains(pkg);
            CheckBox cb = new CheckBox(this);
            cb.setText(allowed ? row[0] + "  · always allowed" : row[0]);
            cb.setTextSize(15);
            cb.setTextColor(Color.parseColor(allowed ? MUTED : NAVY));
            cb.setPadding(dp(8), 0, 0, 0);
            cb.setTag(pkg);
            if (allowed) {
                cb.setChecked(false);
                cb.setEnabled(false);
            } else {
                cb.setChecked(sel.contains(pkg));
                cb.setOnCheckedChangeListener((v, checked) -> {
                    Set<String> s = Link.blocked(MainActivity.this);
                    if (!checked && s.contains(pkg) && Link.blockingNow(MainActivity.this)) {
                        v.setChecked(true);
                        Toast.makeText(MainActivity.this, "Can't unblock during a focus session", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    if (checked) s.add(pkg);
                    else s.remove(pkg);
                    Link.setBlocked(MainActivity.this, s);
                });
                boxes.add(cb);
            }
            line.addView(cb, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
            appList.addView(line);
        }
    }

    private static int rank(String pkg, Set<String> sel) {
        if (sel.contains(pkg)) return 0;
        if (Link.DEFAULT_BLOCKED.contains(pkg)) return 1;
        if (Link.ALWAYS_ALLOWED.contains(pkg)) return 3;
        return 2;
    }

    // ---------- tiny UI helpers ----------
    private LinearLayout card(LinearLayout parent) {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(dp(16), dp(14), dp(16), dp(14));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor(CARD));
        bg.setCornerRadius(dp(16));
        c.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(12);
        parent.addView(c, lp);
        return c;
    }

    private TextView title(String s) {
        TextView t = text(s, 17, NAVY);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding(0, 0, 0, dp(4));
        return t;
    }

    private TextView text(String s, int sp, String color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(Color.parseColor(color));
        return t;
    }

    private Button button(String s) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        return b;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
