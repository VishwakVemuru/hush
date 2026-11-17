package app.hush.phone;

import android.content.ContentValues;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Environment;
import android.provider.MediaStore;
import android.view.View;

import java.io.OutputStream;

/** The bar chart on the screen-time tabs, and the shareable picture. */
final class Charts {
    static final int NAVY = Color.parseColor("#1F3550"), MUTED = Color.parseColor("#8A8274"), LINE = Color.parseColor("#E6DFD1"),
            LAPTOP = Color.parseColor("#3E6A9E"), PHONE = Color.parseColor("#C9A15A");
    static final int[] CAT_COL = {Color.parseColor("#C49A8A"), Color.parseColor("#A99BC4"), Color.parseColor("#C9A15A"),
            Color.parseColor("#B5AD9E"), Color.parseColor("#3E6A9E"), Color.parseColor("#8FA6C4"), Color.parseColor("#7FA7A0"),
            Color.parseColor("#D6CFC1")};

    static int seriesColor(Stats.Result r, int i) {
        return r.combined ? (i == 0 ? LAPTOP : PHONE) : CAT_COL[i];
    }

    static int catColor(String cat) {
        return CAT_COL[Stats.catIndex(cat)];
    }

    /** Stacked bars with soft gridlines. In day view only the waking part of the day is drawn. */
    static class Bars extends View {
        Stats.Result r;
        final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        final float d;

        Bars(Context c) {
            super(c);
            d = c.getResources().getDisplayMetrics().density;
        }

        void set(Stats.Result r) {
            this.r = r;
            invalidate();
        }

        @Override
        protected void onDraw(Canvas c) {
            if (r == null) return;
            int n = r.cols.length, a = 0, b = n - 1;
            if (!r.week) {
                int first = -1, last = -1;
                for (int i = 0; i < n; i++) if (sum(r.cols[i]) > 30) { if (first < 0) first = i; last = i; }
                if (first < 0) { first = 8; last = 22; }
                a = Math.max(0, first - 1);
                b = Math.min(23, last + 1);
                while (b - a < 8) { if (a > 0) a--; if (b - a < 8 && b < 23) b++; if (a == 0 && b == 23) break; }
            }
            long max = 1;
            for (int i = a; i <= b; i++) max = Math.max(max, sum(r.cols[i]));
            long[] steps = {900, 1800, 3600, 5400, 7200, 10800, 14400, 21600, 28800, 43200, 86400};
            long top = 86400;
            for (long s : steps) if (s >= max) { top = s; break; }
            float w = getWidth(), h = getHeight(), labH = 18 * d, left = 30 * d, topPad = 10 * d, ch = h - labH;
            p.setTextSize(10 * d);
            p.setStyle(Paint.Style.FILL);
            for (int g = 0; g <= 2; g++) {
                float y = ch - (ch - topPad) * g / 2f;
                p.setColor(LINE);
                c.drawRect(left, y, w, y + Math.max(1, d), p);
                if (g > 0) {
                    p.setColor(MUTED);
                    long v = top * g / 2;
                    String t = v >= 3600 ? (v % 3600 == 0 ? v / 3600 + "h" : String.format(java.util.Locale.US, "%.1fh", v / 3600f)) : v / 60 + "m";
                    c.drawText(t, 0, y + 4 * d, p);
                }
            }
            int cols = b - a + 1;
            float slot = (w - left) / cols, bw = Math.max(3 * d, slot * 0.62f);
            int every = Math.max(1, (int) Math.ceil(cols / 7.0));
            for (int i = a; i <= b; i++) {
                float x = left + (i - a) * slot + (slot - bw) / 2, y = ch;
                long tot = sum(r.cols[i]);
                if (tot > 30) {
                    float hh = Math.max(3 * d, (ch - topPad) * tot / (float) top);
                    c.save();
                    Path clip = new Path();
                    clip.addRoundRect(new RectF(x, ch - hh, x + bw, ch), new float[]{4 * d, 4 * d, 4 * d, 4 * d, d, d, d, d}, Path.Direction.CW);
                    c.clipPath(clip);
                    for (int s = 0; s < r.cols[i].length; s++) {
                        long v = r.cols[i][s];
                        if (v <= 0) continue;
                        float sh = hh * v / tot;
                        p.setColor(seriesColor(r, s));
                        c.drawRect(x, y - sh, x + bw, y, p);
                        y -= sh;
                    }
                    c.restore();
                } else {
                    p.setColor(LINE);
                    c.drawRect(x, ch - 2 * d, x + bw, ch, p);
                }
                if ((i - a) % every == 0 || (r.week && i == b)) {
                    p.setColor(MUTED);
                    String lab = r.labels[i];
                    c.drawText(lab, x + bw / 2 - p.measureText(lab) / 2, h - 3 * d, p);
                }
            }
        }

        static long sum(long[] a) {
            long s = 0;
            for (long v : a) s += v;
            return s;
        }
    }

    /** 1080x1350 card that matches the laptop's share card. */
    static Bitmap shareCard(Context ctx, Stats.Result r) {
        int W = 1080, H = 1350, P = 90;
        Bitmap bm = Bitmap.createBitmap(W, H, Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(bm);
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setShader(new LinearGradient(0, 0, 0, H, Color.parseColor("#FBF8F2"), Color.parseColor("#EFE8DC"), Shader.TileMode.CLAMP));
        c.drawRect(0, 0, W, H, p);
        p.setShader(null);
        for (int k = 0; k < 2; k++) {
            Path wave = new Path();
            float base = H - (k == 0 ? 170 : 120);
            wave.moveTo(0, base);
            for (int x = 0; x <= W; x += 10) wave.lineTo(x, base + (float) Math.sin(x / (k == 0 ? 90.0 : 70.0) + k * 2) * (k == 0 ? 14 : 12));
            wave.lineTo(W, H);
            wave.lineTo(0, H);
            wave.close();
            p.setColor(Color.argb(k == 0 ? 26 : 41, 62, 106, 158));
            c.drawPath(wave, p);
        }
        Typeface serif = Typeface.create(Typeface.SERIF, Typeface.ITALIC);
        p.setTypeface(serif);
        p.setColor(NAVY);
        p.setTextSize(64);
        c.drawText("hush.", P, 150, p);
        p.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        p.setColor(MUTED);
        p.setTextSize(30);
        String when = r.week ? "This week" : new java.text.SimpleDateFormat("EEEE, d MMMM", java.util.Locale.getDefault()).format(new java.util.Date());
        c.drawText((r.combined ? "Laptop + phone" : "Phone") + " screen time · " + when, P, 215, p);
        p.setTypeface(serif);
        p.setColor(NAVY);
        p.setTextSize(190);
        c.drawText(Stats.dur(r.total), P - 6, 420, p);
        p.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        p.setTextSize(32);
        p.setColor(Color.parseColor("#6E685C"));
        c.drawText(r.sub, P, 480, p);
        // split bar
        float y = 550, bw = W - 2 * P;
        long[] vals;
        int[] cols;
        String[] names;
        if (r.combined) {
            vals = new long[]{r.laptop, r.phone};
            cols = new int[]{LAPTOP, PHONE};
            names = new String[]{"Laptop", "Phone"};
        } else {
            java.util.List<java.util.Map.Entry<String, Long>> cs = new java.util.ArrayList<>(r.cats.entrySet());
            java.util.Collections.sort(cs, (x, z) -> Long.compare(z.getValue(), x.getValue()));
            int k = Math.min(5, cs.size());
            vals = new long[k];
            cols = new int[k];
            names = new String[k];
            for (int i = 0; i < k; i++) { vals[i] = cs.get(i).getValue(); cols[i] = catColor(cs.get(i).getKey()); names[i] = cs.get(i).getKey(); }
        }
        long tot = 0;
        for (long v : vals) tot += v;
        if (tot == 0) tot = 1;
        c.save();
        Path clip = new Path();
        clip.addRoundRect(new RectF(P, y, P + bw, y + 26), 13, 13, Path.Direction.CW);
        c.clipPath(clip);
        float x = P;
        for (int i = 0; i < vals.length; i++) {
            float ww = bw * vals[i] / tot;
            p.setColor(cols[i]);
            c.drawRect(x, y, x + ww + 1, y + 26, p);
            x += ww;
        }
        c.restore();
        y += 70;
        x = P;
        p.setTextSize(28);
        for (int i = 0; i < Math.min(4, vals.length); i++) {
            p.setColor(cols[i]);
            c.drawCircle(x + 9, y - 9, 9, p);
            p.setColor(Color.parseColor("#2B3440"));
            String t = names[i] + " " + Math.round(100.0 * vals[i] / tot) + "%";
            c.drawText(t, x + 28, y, p);
            x += p.measureText(t) + 64;
        }
        y += 90;
        p.setColor(MUTED);
        p.setTextSize(26);
        c.drawText("TOP APPS", P, y, p);
        y += 30;
        long amax = r.apps.isEmpty() ? 1 : r.apps.get(0).secs;
        for (int i = 0; i < Math.min(5, r.apps.size()); i++) {
            Stats.Row a = r.apps.get(i);
            y += 72;
            p.setColor(Color.parseColor("#2B3440"));
            p.setTextSize(36);
            String nm = a.name;
            while (p.measureText(nm) > 430 && nm.length() > 3) nm = nm.substring(0, nm.length() - 2) + "…";
            c.drawText(nm, P, y, p);
            p.setColor(LINE);
            c.drawRoundRect(new RectF(P + 460, y - 20, P + 790, y - 6), 7, 7, p);
            p.setColor(catColor(a.cat));
            c.drawRoundRect(new RectF(P + 460, y - 20, P + 460 + Math.max(14, 330f * a.secs / amax), y - 6), 7, 7, p);
            p.setColor(Color.parseColor("#6E685C"));
            p.setTextSize(32);
            String d = Stats.dur(a.secs);
            c.drawText(d, W - P - p.measureText(d), y, p);
        }
        p.setTypeface(serif);
        p.setColor(NAVY);
        p.setAlpha(140);
        p.setTextSize(34);
        c.drawText("made with hush. · calm focus", P, H - 54, p);
        return bm;
    }

    /** Saves the picture to Pictures/hush (shows up in Gallery) and returns its content Uri for sharing. */
    static Uri save(Context c, Bitmap bm, String name) throws Exception {
        ContentValues v = new ContentValues();
        v.put(MediaStore.Images.Media.DISPLAY_NAME, name + ".png");
        v.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
        v.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/hush");
        Uri uri = c.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v);
        if (uri == null) throw new IllegalStateException("no gallery");
        try (OutputStream os = c.getContentResolver().openOutputStream(uri)) {
            bm.compress(Bitmap.CompressFormat.PNG, 100, os);
        }
        return uri;
    }
}
