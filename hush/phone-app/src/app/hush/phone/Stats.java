package app.hush.phone;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Screen-time numbers for the Phone and Combined tabs. */
final class Stats {
    static final class Row {
        String name, cat, device, pkg;
        long secs;
    }

    static final class Result {
        boolean combined, week;
        long total, phone, laptop, avg;
        int unlocks = -1, blocked;
        String sub = "";
        List<Row> apps = new ArrayList<>();
        Map<String, Long> cats = new HashMap<>();
        // chart: one column per hour (day view) or per day (week view); each column split laptop/phone or by category
        String[] labels;
        long[][] cols;      // [column][series]
        String[] series;    // series names
        boolean hasLaptop;
    }

    static final String[] CATS = {"Social", "Entertainment", "Games", "Browsing", "Study", "Code", "Music", "Other"};

    static int catIndex(String c) {
        for (int i = 0; i < CATS.length; i++) if (CATS[i].equals(c)) return i;
        return CATS.length - 1;
    }

    /** A day of phone data: live from Android for recent days, else the copy kept when it was synced. */
    static JSONObject phoneDay(Context c, int ago) {
        try {
            if (Usage.allowed(c)) {
                Usage.Day d = Usage.day(c, ago);
                if (d.totalMs > 0 || ago == 0) {
                    JSONObject o = Usage.payload(d);
                    JSONObject pk = new JSONObject();
                    for (Usage.App a : d.apps) pk.put(a.name, a.pkg);
                    o.put("pkgs", pk);
                    return o;
                }
            }
            SharedPreferences p = Link.prefs(c);
            return new JSONObject(p.getString("phoneDays", "{}")).optJSONObject(Usage.iso(Usage.startOfDay(ago)));
        } catch (Exception e) {
            return null;
        }
    }

    static JSONObject laptopDay(Context c, int ago) {
        try {
            return new JSONObject(Link.prefs(c).getString("laptopDays", "{}")).optJSONObject(Usage.iso(Usage.startOfDay(ago)));
        } catch (Exception e) {
            return null;
        }
    }

    static Result compute(Context c, boolean combined, boolean week) {
        Result r = new Result();
        r.combined = combined;
        r.week = week;
        int n = week ? 7 : 1;
        Map<String, Row> apps = new HashMap<>();
        r.series = combined ? new String[]{"Laptop", "Phone"} : CATS;
        r.cols = new long[week ? 7 : 24][r.series.length];
        r.labels = new String[r.cols.length];
        String[] dn = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
        for (int i = 0; i < r.cols.length; i++) {
            if (week) {
                java.util.Calendar cal = Usage.startOfDay(6 - i);
                r.labels[i] = i == 6 ? "Today" : dn[cal.get(java.util.Calendar.DAY_OF_WEEK) - 1];
            } else r.labels[i] = i == 0 ? "12a" : i < 12 ? i + "a" : i == 12 ? "12p" : (i - 12) + "p";
        }
        int unlocks = 0;
        boolean anyUnlock = false;
        for (int ago = 0; ago < n; ago++) {
            int col = week ? 6 - ago : -1;
            JSONObject pd = phoneDay(c, ago);
            if (pd != null) {
                long t = pd.optLong("total", 0);
                r.phone += t;
                if (pd.has("unlocks")) { unlocks += pd.optInt("unlocks"); anyUnlock = true; }
                r.blocked += pd.optInt("blocked", 0);
                addApps(apps, r, pd, "phone");
                fill(r, pd, col, combined ? 1 : -1);
            }
            if (combined) {
                JSONObject ld = laptopDay(c, ago);
                if (ld != null) {
                    r.hasLaptop = true;
                    r.laptop += ld.optLong("total", 0);
                    addApps(apps, r, ld, "laptop");
                    fill(r, ld, col, 0);
                }
            }
        }
        r.total = r.phone + (combined ? r.laptop : 0);
        if (anyUnlock) r.unlocks = unlocks;
        r.apps.addAll(apps.values());
        Collections.sort(r.apps, (a, b) -> Long.compare(b.secs, a.secs));
        if (r.apps.size() > 12) r.apps = new ArrayList<>(r.apps.subList(0, 12));
        // compare with the past week (day view only)
        if (!week) {
            long sum = 0;
            int k = 0;
            for (int ago = 1; ago <= 7; ago++) {
                long t = 0;
                JSONObject pd = phoneDay(c, ago);
                if (pd != null) t += pd.optLong("total", 0);
                if (combined) {
                    JSONObject ld = laptopDay(c, ago);
                    if (ld != null) t += ld.optLong("total", 0);
                }
                if (t > 0) { sum += t; k++; }
            }
            if (k > 0) {
                r.avg = sum / k;
                long diff = r.total - r.avg;
                r.sub = Math.abs(diff) < 60 ? "same as usual" : (diff > 0 ? "↑ " : "↓ ") + dur(Math.abs(diff)) + " vs your average";
            } else r.sub = "first day tracked";
        } else {
            int active = 0;
            for (long[] col : r.cols) { long s = 0; for (long v : col) s += v; if (s > 0) active++; }
            r.avg = active > 0 ? r.total / active : 0;
            r.sub = "avg " + dur(r.avg) + " a day";
        }
        return r;
    }

    private static void addApps(Map<String, Row> apps, Result r, JSONObject d, String device) {
        JSONArray a = d.optJSONArray("apps");
        JSONObject pkgs = d.optJSONObject("pkgs");
        if (a == null) return;
        for (int i = 0; i < a.length(); i++) {
            JSONArray x = a.optJSONArray(i);
            if (x == null) continue;
            String name = x.optString(0), cat = x.optString(1, "Other");
            long secs = x.optLong(2);
            String key = r.combined ? device + "|" + name : name;
            Row row = apps.get(key);
            if (row == null) {
                row = new Row();
                row.name = name;
                row.cat = cat;
                row.device = device;
                row.pkg = pkgs != null ? pkgs.optString(name, null) : null;
                apps.put(key, row);
            }
            row.secs += secs;
            Long cur = r.cats.get(cat);
            r.cats.put(cat, (cur == null ? 0 : cur) + secs);
        }
    }

    /** Add a day into the chart: whole day into one column (week), or hour by hour (day). */
    private static void fill(Result r, JSONObject d, int col, int deviceSeries) {
        if (r.week) {
            if (deviceSeries >= 0) r.cols[col][deviceSeries] += d.optLong("total", 0);
            else {
                JSONArray a = d.optJSONArray("apps");
                if (a == null) return;
                for (int i = 0; i < a.length(); i++) {
                    JSONArray x = a.optJSONArray(i);
                    if (x != null) r.cols[col][catIndex(x.optString(1))] += x.optLong(2);
                }
            }
            return;
        }
        JSONArray hours = d.optJSONArray("hours");
        if (hours == null) return;
        for (int h = 0; h < Math.min(24, hours.length()); h++) {
            JSONObject b = hours.optJSONObject(h);
            if (b == null) continue;
            for (java.util.Iterator<String> it = b.keys(); it.hasNext(); ) {
                String cat = it.next();
                long s = b.optLong(cat);
                if (deviceSeries >= 0) r.cols[h][deviceSeries] += s;
                else r.cols[h][catIndex(cat)] += s;
            }
        }
    }

    static String dur(long secs) {
        long m = Math.round(secs / 60.0), h = m / 60;
        return h > 0 ? h + "h " + (m % 60) + "m" : m + "m";
    }
}
