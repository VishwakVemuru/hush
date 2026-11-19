package app.hush.phone;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class MainActivity extends Activity {
    private static final String NAVY = "#1F3550", MUTED = "#8A8274", BG = "#F3EFE7", CARD = "#FBF8F2", MOSS = "#5E8A5A",
            SIDE = "#EBE5D9", LINE = "#E6DFD1";
    private final Handler h = new Handler(Looper.getMainLooper());
    private int tab = 0;            // 0 phone, 1 combined, 2 friends, 3 blocking
    private boolean week = false;
    private LinearLayout body;
    private final TextView[] tabBtns = new TextView[4];
    private Stats.Result shown;
    private final Map<String, String> labelToPkg = new HashMap<>();

    // blocking tab
    private TextView status, a11yText;
    private Button a11yBtn;
    private EditText codeIn;
    private final List<CheckBox> boxes = new ArrayList<>();

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(Color.parseColor(BG));
        getWindow().setNavigationBarColor(Color.parseColor(BG));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor(BG));

        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.VERTICAL);
        top.setPadding(dp(20), dp(22), dp(20), dp(8));
        TextView logo = text("hush.", 36, NAVY);
        logo.setTypeface(Typeface.create(Typeface.SERIF, Typeface.ITALIC));
        top.addView(logo);
        LinearLayout tabs = new LinearLayout(this);
        tabs.setPadding(dp(3), dp(3), dp(3), dp(3));
        tabs.setBackground(round(SIDE, 999));
        String[] names = {"Phone", "Combined", "Friends", "Blocking"};
        for (int i = 0; i < 4; i++) {
            final int k = i;
            TextView t = text(names[i], 14, MUTED);
            t.setGravity(Gravity.CENTER);
            t.setPadding(0, dp(8), 0, dp(8));
            t.setOnClickListener(v -> showTab(k));
            tabBtns[i] = t;
            tabs.addView(t, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        }
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        tlp.topMargin = dp(12);
        top.addView(tabs, tlp);
        root.addView(top);

        ScrollView sv = new ScrollView(this);
        body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(16), dp(6), dp(16), dp(40));
        sv.addView(body);
        root.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
        loadLabels();
        showTab(Link.prefs(this).getString("code", "").isEmpty() ? 3 : 0);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (tab == 3) refresh.run();
        else if (tab == 2) renderFriends();
        else render();
        // pull fresh numbers in the background, then redraw
        new Thread(() -> {
            Cloud.syncQuietly(MainActivity.this);
            h.post(() -> { if (tab < 2) render(); });
        }).start();
    }

    @Override
    protected void onPause() {
        h.removeCallbacks(refresh);
        super.onPause();
    }

    private void showTab(int k) {
        tab = k;
        for (int i = 0; i < 4; i++) {
            TextView t = tabBtns[i];
            t.setBackground(i == k ? round(CARD, 999) : null);
            t.setTextColor(Color.parseColor(i == k ? NAVY : MUTED));
            t.setTypeface(i == k ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        }
        h.removeCallbacks(refresh);
        body.removeAllViews();
        if (k == 3) { buildBlocking(); refresh.run(); }
        else if (k == 2) renderFriends();
        else render();
    }

    // =====================================================================
    // Screen time tabs
    // =====================================================================
    private void render() {
        if (tab >= 2) return;
        final boolean combined = tab == 1;
        final boolean wk = week;
        final int myTab = tab;
        if (!Usage.allowed(this) && !combined) {
            body.removeAllViews();
            LinearLayout c = card(body);
            c.addView(title("See your phone screen time"));
            c.addView(text("hush. needs Usage access to read how long you use each app. It stays on your phone and your own sync.", 14, MUTED));
            Button go = button("Allow usage access");
            go.setOnClickListener(v -> openUsageAccess());
            c.addView(go);
            return;
        }
        new Thread(() -> {
            final Stats.Result r = Stats.compute(MainActivity.this, combined, wk);
            h.post(() -> { if (tab == myTab && week == wk) draw(r); });
        }).start();
    }

    private void draw(Stats.Result r) {
        shown = r;
        body.removeAllViews();
        // range toggle + share
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout seg = new LinearLayout(this);
        seg.setPadding(dp(3), dp(3), dp(3), dp(3));
        seg.setBackground(round(SIDE, 999));
        String[] rn = {"Today", "Week"};
        for (int i = 0; i < 2; i++) {
            final boolean w = i == 1;
            TextView t = text(rn[i], 13, w == week ? NAVY : MUTED);
            t.setPadding(dp(16), dp(6), dp(16), dp(6));
            if (w == week) { t.setBackground(round(CARD, 999)); t.setTypeface(Typeface.DEFAULT_BOLD); }
            t.setOnClickListener(v -> { week = w; render(); });
            seg.addView(t);
        }
        bar.addView(seg);
        View sp = new View(this);
        bar.addView(sp, new LinearLayout.LayoutParams(0, 1, 1));
        TextView share = text("Share", 14, NAVY);
        share.setPadding(dp(16), dp(8), dp(16), dp(8));
        share.setBackground(roundStroke(CARD, LINE, 999));
        share.setOnClickListener(v -> share());
        bar.addView(share);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        blp.bottomMargin = dp(12);
        body.addView(bar, blp);

        if (r.combined && !r.hasLaptop) {
            LinearLayout c = card(body);
            c.addView(title("Laptop not synced yet"));
            c.addView(text(Cloud.configured(this)
                    ? "Waiting for your laptop's numbers. Make sure hush. is running on it."
                    : "Connect to the same Wi-Fi as your laptop once (with hush. open) so this phone can pick up the sync settings.", 14, MUTED));
        }

        // hero
        LinearLayout hero = card(body);
        hero.addView(text(r.combined ? "Total screen time" : "Phone screen time", 13, MUTED));
        TextView big = text(Stats.dur(r.total), 46, NAVY);
        big.setTypeface(Typeface.create(Typeface.SERIF, Typeface.ITALIC));
        hero.addView(big);
        TextView sub = text(r.sub, 13, r.sub.startsWith("↓") ? MOSS : MUTED);
        hero.addView(sub);
        hero.addView(splitBar(r));

        // mini metrics
        LinearLayout row = new LinearLayout(this);
        if (r.combined) {
            row.addView(metric("Laptop", Stats.dur(r.laptop)), weight());
            row.addView(metric("Phone", Stats.dur(r.phone)), weight());
        } else {
            row.addView(metric("Unlocks", r.unlocks >= 0 ? String.valueOf(r.unlocks) : "–"), weight());
            row.addView(metric("Blocked", String.valueOf(r.blocked)), weight());
        }
        LinearLayout.LayoutParams rlp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        rlp.bottomMargin = dp(12);
        body.addView(row, rlp);

        // chart
        LinearLayout cc = card(body);
        cc.addView(text(r.week ? "Per day" : "By hour", 13, MUTED));
        Charts.Bars chart = new Charts.Bars(this);
        chart.set(r);
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(170));
        clp.topMargin = dp(10);
        cc.addView(chart, clp);
        cc.addView(legend(r));

        // apps
        LinearLayout ac = card(body);
        ac.addView(text(r.combined ? "Top apps on both" : "Top apps", 13, MUTED));
        if (r.apps.isEmpty()) ac.addView(text("Nothing yet. Use your phone and check back.", 14, MUTED));
        long max = r.apps.isEmpty() ? 1 : r.apps.get(0).secs;
        for (Stats.Row a : r.apps) ac.addView(appRow(a, max, r.combined));

        long ok = Link.prefs(this).getLong("lastSync", 0);
        TextView foot = text(Cloud.configured(this) ? (ok > 0 ? "Synced " + ago(ok) : "Not synced yet") : "Cloud sync not set up yet", 12, MUTED);
        foot.setGravity(Gravity.CENTER);
        foot.setPadding(0, dp(6), 0, 0);
        body.addView(foot);
    }

    private View splitBar(Stats.Result r) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.setPadding(0, dp(12), 0, 0);
        LinearLayout barv = new LinearLayout(this);
        barv.setBackground(round(LINE, 4));
        List<long[]> parts = new ArrayList<>();
        List<String> names = new ArrayList<>();
        if (r.combined) {
            parts.add(new long[]{r.laptop, Charts.LAPTOP});
            names.add("Laptop");
            parts.add(new long[]{r.phone, Charts.PHONE});
            names.add("Phone");
        } else {
            List<Map.Entry<String, Long>> cs = new ArrayList<>(r.cats.entrySet());
            Collections.sort(cs, (x, z) -> Long.compare(z.getValue(), x.getValue()));
            for (int i = 0; i < Math.min(5, cs.size()); i++) {
                parts.add(new long[]{cs.get(i).getValue(), Charts.catColor(cs.get(i).getKey())});
                names.add(cs.get(i).getKey());
            }
        }
        long tot = 0;
        for (long[] p : parts) tot += p[0];
        if (tot == 0) return wrap;
        for (long[] p : parts) {
            if (p[0] <= 0) continue;
            View v = new View(this);
            v.setBackgroundColor((int) p[1]);
            barv.addView(v, new LinearLayout.LayoutParams(0, dp(8), p[0]));
        }
        barv.setClipToOutline(true);
        wrap.addView(barv);
        LinearLayout key = new LinearLayout(this);
        key.setPadding(0, dp(8), 0, 0);
        for (int i = 0; i < Math.min(4, parts.size()); i++) {
            if (parts.get(i)[0] * 100 < tot) continue; // skip slivers under 1%
            TextView t = text("● " + names.get(i) + " " + Math.round(100.0 * parts.get(i)[0] / tot) + "%", 12, "#6E685C");
            t.setTextColor((int) parts.get(i)[1]);
            t.setPadding(0, 0, dp(14), 0);
            key.addView(t);
        }
        wrap.addView(key);
        return wrap;
    }

    private View legend(Stats.Result r) {
        LinearLayout l = new LinearLayout(this);
        l.setPadding(0, dp(8), 0, 0);
        boolean[] used = new boolean[r.series.length];
        for (long[] col : r.cols) for (int s = 0; s < col.length; s++) if (col[s] > 0) used[s] = true;
        int shownCount = 0;
        for (int s = 0; s < r.series.length && shownCount < 5; s++) {
            if (!used[s]) continue;
            TextView t = text("● " + r.series[s], 12, MUTED);
            t.setTextColor(Charts.seriesColor(r, s));
            t.setPadding(0, 0, dp(12), 0);
            l.addView(t);
            shownCount++;
        }
        return l;
    }

    private View appRow(Stats.Row a, long max, boolean combined) {
        LinearLayout line = new LinearLayout(this);
        line.setGravity(Gravity.CENTER_VERTICAL);
        line.setPadding(0, dp(8), 0, dp(8));
        ImageView icon = new ImageView(this);
        String pkg = a.pkg != null ? a.pkg : labelToPkg.get(a.name);
        Drawable d = null;
        if (pkg != null && "phone".equals(a.device)) {
            try { d = getPackageManager().getApplicationIcon(pkg); } catch (Exception ignored) { }
        }
        if (d != null) icon.setImageDrawable(d);
        else {
            GradientDrawable g = round(String.format("#%06X", 0xFFFFFF & Charts.catColor(a.cat)), 8);
            g.setAlpha(60);
            icon.setBackground(g);
        }
        line.addView(icon, new LinearLayout.LayoutParams(dp(32), dp(32)));
        LinearLayout mid = new LinearLayout(this);
        mid.setOrientation(LinearLayout.VERTICAL);
        mid.setPadding(dp(12), 0, dp(12), 0);
        TextView nm = text(a.name + (combined ? ("phone".equals(a.device) ? "  · phone" : "  · laptop") : ""), 15, "#2B3440");
        nm.setSingleLine(true);
        mid.addView(nm);
        FrameLayout track = new FrameLayout(this);
        track.setBackground(round(LINE, 3));
        View fill = new View(this);
        fill.setBackground(round(String.format("#%06X", 0xFFFFFF & Charts.catColor(a.cat)), 3));
        track.addView(fill, new FrameLayout.LayoutParams(0, dp(6)));
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(6));
        tlp.topMargin = dp(6);
        mid.addView(track, tlp);
        final float frac = a.secs / (float) Math.max(1, max);
        track.post(() -> {
            ViewGroup.LayoutParams lp = fill.getLayoutParams();
            lp.width = Math.max(dp(4), (int) (track.getWidth() * frac));
            fill.setLayoutParams(lp);
        });
        line.addView(mid, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        line.addView(text(Stats.dur(a.secs), 14, "#6E685C"));
        return line;
    }

    private View metric(String k, String v) {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(dp(16), dp(12), dp(16), dp(12));
        c.setBackground(roundStroke(CARD, LINE, 16));
        c.addView(text(k, 13, MUTED));
        TextView t = text(v, 26, NAVY);
        t.setTypeface(Typeface.create(Typeface.SERIF, Typeface.NORMAL));
        c.addView(t);
        return c;
    }

    private LinearLayout.LayoutParams weight() {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        lp.setMarginEnd(dp(6));
        lp.setMarginStart(dp(6));
        return lp;
    }

    private void share() {
        if (shown == null) return;
        try {
            Bitmap bm = Charts.shareCard(this, shown);
            String name = "hush-" + (shown.combined ? "combined" : "phone") + "-" + (shown.week ? "week" : "today") + "-" + System.currentTimeMillis();
            Uri uri = Charts.save(this, bm, name);
            Intent send = new Intent(Intent.ACTION_SEND).setType("image/png").putExtra(Intent.EXTRA_STREAM, uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(Intent.createChooser(send, "Share your screen time"));
            Toast.makeText(this, "Saved to Pictures/hush", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Toast.makeText(this, "Couldn't make the picture", Toast.LENGTH_SHORT).show();
        }
    }

    private void openUsageAccess() {
        try {
            startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS, Uri.parse("package:" + getPackageName())));
        } catch (Exception e) {
            try { startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)); } catch (Exception ignored) { }
        }
    }

    private void loadLabels() {
        try {
            PackageManager pm = getPackageManager();
            for (ResolveInfo r : pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0))
                labelToPkg.put(r.loadLabel(pm).toString(), r.activityInfo.packageName);
        } catch (Exception ignored) {
        }
    }

    private static String ago(long t) {
        long m = (System.currentTimeMillis() - t) / 60000;
        return m < 1 ? "just now" : m < 60 ? m + " min ago" : (m / 60) + " h ago";
    }


    // =====================================================================
    // Friends tab: account + leaderboard
    // =====================================================================
    private boolean lbWeek = true;

    private void renderFriends() {
        body.removeAllViews();
        if (Cloud.username(this).isEmpty()) {
            LinearLayout c = card(body);
            c.addView(title("Sign in to hush."));
            c.addView(text("Use the same account as on your laptop to see the friends leaderboard. No account yet? Create one in the laptop app (Friends tab).", 14, MUTED));
            final EditText u = new EditText(this);
            u.setHint("Username");
            u.setSingleLine(true);
            c.addView(u);
            final EditText pw = new EditText(this);
            pw.setHint("Password");
            pw.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
            c.addView(pw);
            final TextView err = text("", 13, "#A0522D");
            c.addView(err);
            Button go = button("Sign in");
            go.setOnClickListener(v -> {
                go.setEnabled(false);
                final String un = u.getText().toString().trim().toLowerCase(), ps = pw.getText().toString();
                new Thread(() -> {
                    final String e = Cloud.login(MainActivity.this, un, ps);
                    if (e == null) Cloud.syncQuietly(MainActivity.this);
                    h.post(() -> {
                        go.setEnabled(true);
                        if (e != null) err.setText(e);
                        else { Toast.makeText(MainActivity.this, "Signed in as @" + Cloud.username(MainActivity.this), Toast.LENGTH_SHORT).show(); renderFriends(); }
                    });
                }).start();
            });
            c.addView(go);
            return;
        }
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout seg = new LinearLayout(this);
        seg.setPadding(dp(3), dp(3), dp(3), dp(3));
        seg.setBackground(round(SIDE, 999));
        String[] rn = {"Today", "Week"};
        for (int i = 0; i < 2; i++) {
            final boolean w = i == 1;
            TextView t = text(rn[i], 13, w == lbWeek ? NAVY : MUTED);
            t.setPadding(dp(16), dp(6), dp(16), dp(6));
            if (w == lbWeek) { t.setBackground(round(CARD, 999)); t.setTypeface(Typeface.DEFAULT_BOLD); }
            t.setOnClickListener(v -> { lbWeek = w; renderFriends(); });
            seg.addView(t);
        }
        bar.addView(seg);
        View sp = new View(this);
        bar.addView(sp, new LinearLayout.LayoutParams(0, 1, 1));
        TextView who = text("@" + Cloud.username(this), 13, MUTED);
        who.setOnLongClickListener(v -> { Cloud.logout(MainActivity.this); renderFriends(); return true; });
        bar.addView(who);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        blp.bottomMargin = dp(12);
        body.addView(bar, blp);
        final LinearLayout lb = card(body);
        lb.addView(text("Leaderboard · verified = camera saw you studying", 13, MUTED));
        final TextView loading = text("Loading…", 14, MUTED);
        lb.addView(loading);
        final boolean wk = lbWeek;
        new Thread(() -> {
            org.json.JSONArray rows = null;
            String err = null;
            try { rows = Cloud.leaderboard(MainActivity.this, wk).optJSONArray("rows"); } catch (Exception e) { err = "Can't load the leaderboard right now."; }
            final org.json.JSONArray fr = rows;
            final String fe = err;
            h.post(() -> {
                if (tab != 2 || lbWeek != wk) return;
                lb.removeView(loading);
                if (fe != null || fr == null) { lb.addView(text(fe != null ? fe : "Nothing yet.", 14, MUTED)); return; }
                long max = 1;
                for (int i = 0; i < fr.length(); i++) max = Math.max(max, fr.optJSONObject(i).optLong("focus_s"));
                for (int i = 0; i < fr.length(); i++) lb.addView(lbRow(i, fr.optJSONObject(i), max));
                if (fr.length() < 2) lb.addView(text("Add friends by username in the laptop app and you'll compete here.", 13, MUTED));
            });
        }).start();
        TextView hint = text("Long-press your username to sign out.", 12, MUTED);
        hint.setGravity(Gravity.CENTER);
        body.addView(hint);
    }

    private View lbRow(int i, org.json.JSONObject x, long max) {
        LinearLayout line = new LinearLayout(this);
        line.setGravity(Gravity.CENTER_VERTICAL);
        line.setPadding(dp(8), dp(10), dp(8), dp(10));
        if (x.optBoolean("me")) line.setBackground(round("#E3EAF3", 12));
        TextView rk = text(String.valueOf(i + 1), 18, i == 0 && x.optLong("verified_s") > 0 ? "#C9A15A" : MUTED);
        rk.setTypeface(Typeface.create(Typeface.SERIF, Typeface.NORMAL));
        line.addView(rk, new LinearLayout.LayoutParams(dp(26), ViewGroup.LayoutParams.WRAP_CONTENT));
        LinearLayout mid = new LinearLayout(this);
        mid.setOrientation(LinearLayout.VERTICAL);
        String streak = x.optInt("streak") > 0 ? "  · " + x.optInt("streak") + "d streak" : "";
        TextView nm = text(x.optString("display") + (x.optBoolean("me") ? "  (you)" : ""), 15, "#2B3440");
        nm.setSingleLine(true);
        mid.addView(nm);
        mid.addView(text("@" + x.optString("username") + streak, 12, MUTED));
        FrameLayout track = new FrameLayout(this);
        track.setBackground(round(LINE, 3));
        final View all = new View(this), ver = new View(this);
        all.setBackground(round("#C7D3E2", 3));
        ver.setBackground(round(MOSS, 3));
        track.addView(all, new FrameLayout.LayoutParams(0, dp(6)));
        track.addView(ver, new FrameLayout.LayoutParams(0, dp(6)));
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(6));
        tlp.topMargin = dp(6);
        mid.addView(track, tlp);
        final float fa = x.optLong("focus_s") / (float) max, fv = x.optLong("verified_s") / (float) max;
        track.post(() -> {
            ViewGroup.LayoutParams a = all.getLayoutParams(); a.width = (int) (track.getWidth() * fa); all.setLayoutParams(a);
            ViewGroup.LayoutParams v = ver.getLayoutParams(); v.width = (int) (track.getWidth() * fv); ver.setLayoutParams(v);
        });
        LinearLayout.LayoutParams mlp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        mlp.setMarginStart(dp(8));
        mlp.setMarginEnd(dp(12));
        line.addView(mid, mlp);
        LinearLayout nums = new LinearLayout(this);
        nums.setOrientation(LinearLayout.VERTICAL);
        nums.setGravity(Gravity.END);
        TextView v1 = text(Stats.dur(x.optLong("verified_s")), 16, MOSS);
        v1.setTypeface(Typeface.DEFAULT_BOLD);
        nums.addView(v1);
        nums.addView(text(Stats.dur(x.optLong("focus_s")) + " focus", 12, MUTED));
        line.addView(nums);
        return line;
    }

    // =====================================================================
    // Blocking tab (pairing, accessibility, app picker)
    // =====================================================================
    private void buildBlocking() {
        boxes.clear();
        LinearLayout st = card(body);
        status = text("…", 17, NAVY);
        st.addView(status);

        LinearLayout pair = card(body);
        pair.addView(title("1 · Pair with your laptop"));
        pair.addView(text("In hush. on your laptop, open Settings → Phone and type the 8-digit code here. Both need to be on the same Wi-Fi the first time.", 14, MUTED));
        codeIn = new EditText(this);
        codeIn.setInputType(InputType.TYPE_CLASS_NUMBER);
        codeIn.setHint("Pairing code");
        codeIn.setTextSize(22);
        codeIn.setText(Link.prefs(this).getString("code", ""));
        pair.addView(codeIn);
        Button connect = button("Connect");
        connect.setOnClickListener(v -> connect());
        pair.addView(connect);

        LinearLayout acc = card(body);
        acc.addView(title("2 · Turn on blocking"));
        a11yText = text("", 14, MUTED);
        acc.addView(a11yText);
        a11yBtn = button("Open accessibility settings");
        a11yBtn.setOnClickListener(v -> {
            try { startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)); } catch (Exception e) { startActivity(new Intent(Settings.ACTION_SETTINGS)); }
        });
        acc.addView(a11yBtn);
        Button info = button("App info (for \"Allow restricted settings\")");
        info.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName()))));
        acc.addView(info);

        LinearLayout use = card(body);
        use.addView(title("3 · Screen time"));
        boolean ua = Usage.allowed(this);
        use.addView(text(ua ? "Usage access is on. Your phone's screen time shows in the Phone and Combined tabs, and on your laptop."
                : "Allow Usage access so hush. can show your phone's screen time here and on your laptop.", 14, MUTED));
        if (!ua) {
            Button g = button("Allow usage access");
            g.setOnClickListener(v -> openUsageAccess());
            use.addView(g);
        }

        LinearLayout apps = card(body);
        apps.addView(title("4 · Apps to block during focus"));
        apps.addView(text("WhatsApp, Telegram and Discord are never blocked. While a session is running you can add apps but not remove them.", 14, MUTED));
        LinearLayout appList = new LinearLayout(this);
        appList.setOrientation(LinearLayout.VERTICAL);
        apps.addView(appList);
        buildAppList(appList);
    }

    private final Runnable refresh = new Runnable() {
        public void run() {
            if (tab != 3) return;
            updateStatus();
            h.postDelayed(this, 2000);
        }
    };

    private boolean a11yOn() {
        String s = Settings.Secure.getString(getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        return s != null && s.contains(getPackageName() + "/");
    }

    private void updateStatus() {
        if (status == null) return;
        SharedPreferences p = Link.prefs(this);
        boolean enabled = a11yOn();
        boolean stalled = enabled && !BlockService.running;
        boolean on = enabled && BlockService.running;
        a11yText.setText(on
                ? "Blocking is on. You can close this app; blocking keeps running."
                : stalled
                ? "Your phone stopped the blocker. In accessibility settings, turn hush. off and on again. To stop it happening: Settings → Apps → hush. → Autostart on, and Battery saver → No restrictions."
                : "Find \"hush.\" under Downloaded apps (or Installed services) and turn it on. If it's greyed out: App info → ⋮ → Allow restricted settings, then try again.");
        a11yBtn.setVisibility(on ? View.GONE : View.VISIBLE);
        String code = p.getString("code", "");
        long now = System.currentTimeMillis(), until = Link.blockUntil(this), lastOk = p.getLong("lastOk", 0), lastCloud = p.getLong("lastCloud", 0);
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
            if (now - lastOk > 20000) msg += now - lastCloud < 90000 ? "\n(via the cloud)" : "\n(laptop out of reach, still blocking)";
            color = MOSS;
        } else if (s == Link.WRONG_CODE) msg = "Wrong code. Check Settings → Phone on the laptop.";
        else if (now - lastOk < 20000) msg = "Connected. Waiting for the laptop to start focus.";
        else if (now - lastCloud < 90000) msg = "Connected through the cloud. Waiting for the laptop to start focus.";
        else msg = "Looking for your laptop… Is hush. open on it?";
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
        Link.prefs(this).edit().putString("code", code).putString("laptopId", "").putInt("fails", 99).putLong("lastScan", 0)
                .putLong("cfgTry", 0).apply();
        status.setText("Looking for your laptop…");
        new Thread(() -> {
            final int r = Link.poll(MainActivity.this);
            if (r == Link.OK) Cloud.syncQuietly(MainActivity.this);
            h.post(() -> {
                Toast.makeText(MainActivity.this, r == Link.OK ? "Paired with your laptop" : r == Link.WRONG_CODE
                        ? "Laptop found, but the code is wrong" : "Couldn't find hush. on this Wi-Fi", Toast.LENGTH_LONG).show();
                updateStatus();
            });
        }).start();
    }

    private void buildAppList(LinearLayout appList) {
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
            try { icon.setImageDrawable(pm.getApplicationIcon(pkg)); } catch (Exception ignored) { }
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
        c.setBackground(roundStroke(CARD, LINE, 18));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(12);
        parent.addView(c, lp);
        return c;
    }

    private GradientDrawable round(String color, int radiusDp) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(Color.parseColor(color));
        g.setCornerRadius(dp(radiusDp));
        return g;
    }

    private GradientDrawable roundStroke(String color, String stroke, int radiusDp) {
        GradientDrawable g = round(color, radiusDp);
        g.setStroke(Math.max(1, dp(1) / 2 + 1), Color.parseColor(stroke));
        return g;
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
