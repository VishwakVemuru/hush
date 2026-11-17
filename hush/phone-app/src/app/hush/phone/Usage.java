package app.hush.phone;

import android.app.AppOpsManager;
import android.app.usage.UsageEvents;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Process;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** Phone screen time from Android's own usage log (needs the user to allow "Usage access"). */
final class Usage {
    static final class App {
        String pkg, name, cat;
        long ms;
    }

    static final class Day {
        String date;
        long totalMs;
        int unlocks;
        List<App> apps = new ArrayList<>();
        Map<String, Long>[] hours;
    }

    static boolean allowed(Context c) {
        try {
            AppOpsManager ops = (AppOpsManager) c.getSystemService(Context.APP_OPS_SERVICE);
            int mode = ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.getPackageName());
            return mode == AppOpsManager.MODE_ALLOWED;
        } catch (Throwable t) {
            return false;
        }
    }

    static String iso(Calendar cal) {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(cal.getTime());
    }

    static Calendar startOfDay(int daysAgo) {
        Calendar cal = Calendar.getInstance();
        cal.set(Calendar.HOUR_OF_DAY, 0);
        cal.set(Calendar.MINUTE, 0);
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        cal.add(Calendar.DAY_OF_YEAR, -daysAgo);
        return cal;
    }

    /** Category in hush.'s words. Chat apps count as Social; browsers as Browsing. */
    static String category(Context c, String pkg) {
        if (pkg.contains("whatsapp") || pkg.contains("telegram") || pkg.equals("com.discord") || pkg.contains("instagram")
                || pkg.contains("snapchat") || pkg.contains("facebook") || pkg.contains("twitter") || pkg.contains("reddit")) return "Social";
        if (pkg.contains("youtube") || pkg.contains("netflix") || pkg.contains("hotstar") || pkg.contains("primevideo") || pkg.contains("musically") || pkg.contains("trill")) return "Entertainment";
        if (pkg.contains("chrome") || pkg.contains("brave") || pkg.contains("opera") || pkg.contains("firefox") || pkg.contains("browser")) return "Browsing";
        if (pkg.contains("spotify") || pkg.contains("music")) return "Music";
        try {
            int cat = c.getPackageManager().getApplicationInfo(pkg, 0).category;
            switch (cat) {
                case ApplicationInfo.CATEGORY_GAME: return "Games";
                case ApplicationInfo.CATEGORY_AUDIO: return "Music";
                case ApplicationInfo.CATEGORY_VIDEO: case ApplicationInfo.CATEGORY_IMAGE: return "Entertainment";
                case ApplicationInfo.CATEGORY_SOCIAL: return "Social";
                case ApplicationInfo.CATEGORY_NEWS: return "Browsing";
                case ApplicationInfo.CATEGORY_PRODUCTIVITY: return "Study";
                default: return "Other";
            }
        } catch (Exception e) {
            return "Other";
        }
    }

    static String label(Context c, String pkg) {
        try {
            PackageManager pm = c.getPackageManager();
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (Exception e) {
            return pkg;
        }
    }

    /** Launchers and system UI aren't "screen time on an app". */
    static Set<String> ignored(Context c) {
        Set<String> s = new HashSet<>();
        s.add("com.android.systemui");
        s.add(c.getPackageName());
        try {
            Intent i = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
            for (ResolveInfo r : c.getPackageManager().queryIntentActivities(i, PackageManager.MATCH_ALL)) s.add(r.activityInfo.packageName);
        } catch (Exception ignored) {
        }
        return s;
    }

    /** One day of usage, built from foreground/background events (more accurate than the daily buckets). */
    @SuppressWarnings("unchecked")
    static Day day(Context c, int daysAgo) {
        Day d = new Day();
        Calendar start = startOfDay(daysAgo);
        d.date = iso(start);
        d.hours = new Map[24];
        for (int i = 0; i < 24; i++) d.hours[i] = new HashMap<>();
        if (!allowed(c)) return d;
        long from = start.getTimeInMillis(), to = Math.min(from + 86400000L, System.currentTimeMillis());
        UsageStatsManager usm = (UsageStatsManager) c.getSystemService(Context.USAGE_STATS_SERVICE);
        Set<String> skip = ignored(c);
        Map<String, Long> open = new HashMap<>();
        Map<String, App> apps = new HashMap<>();
        // start a little early so an app already open at midnight is counted from midnight
        UsageEvents ev = usm.queryEvents(from - 3 * 3600000L, to);
        UsageEvents.Event e = new UsageEvents.Event();
        String fg = null;
        long fgSince = 0;
        while (ev.hasNextEvent()) {
            ev.getNextEvent(e);
            int t = e.getEventType();
            long ts = e.getTimeStamp();
            String p = e.getPackageName();
            if (t == 18 /* KEYGUARD_HIDDEN = unlock */ && ts >= from) { d.unlocks++; continue; }
            if (t == UsageEvents.Event.SCREEN_NON_INTERACTIVE || t == 17 /* KEYGUARD_SHOWN */) {
                if (fg != null) add(c, d, apps, skip, fg, Math.max(fgSince, from), ts);
                fg = null;
                continue;
            }
            if (t == UsageEvents.Event.ACTIVITY_RESUMED) {
                if (fg != null && !fg.equals(p)) add(c, d, apps, skip, fg, Math.max(fgSince, from), ts);
                if (fg == null || !fg.equals(p)) { fg = p; fgSince = ts; }
            } else if (t == UsageEvents.Event.ACTIVITY_PAUSED || t == UsageEvents.Event.ACTIVITY_STOPPED) {
                if (p.equals(fg)) {
                    add(c, d, apps, skip, fg, Math.max(fgSince, from), ts);
                    fg = null;
                }
            }
        }
        if (fg != null) add(c, d, apps, skip, fg, Math.max(fgSince, from), to);
        d.apps.addAll(apps.values());
        Collections.sort(d.apps, (a, b) -> Long.compare(b.ms, a.ms));
        for (App a : d.apps) d.totalMs += a.ms;
        return d;
    }

    private static void add(Context c, Day d, Map<String, App> apps, Set<String> skip, String pkg, long a, long b) {
        if (b <= a || skip.contains(pkg)) return;
        Calendar cal = Calendar.getInstance();
        cal.setTimeInMillis(a);
        long from = startOfDayOf(a);
        long ms = b - a;
        if (ms > 6 * 3600000L) return; // a missed "paused" event; don't invent hours of use
        App app = apps.get(pkg);
        if (app == null) {
            app = new App();
            app.pkg = pkg;
            app.name = label(c, pkg);
            app.cat = category(c, pkg);
            apps.put(pkg, app);
        }
        app.ms += ms;
        // spread across hour buckets
        long t = a;
        while (t < b) {
            cal.setTimeInMillis(t);
            int h = cal.get(Calendar.HOUR_OF_DAY);
            long nextHour = from + (long) (h + 1) * 3600000L;
            long chunk = Math.min(b, nextHour) - t;
            Long cur = d.hours[h].get(app.cat);
            d.hours[h].put(app.cat, (cur == null ? 0 : cur) + chunk);
            t += chunk;
        }
    }

    private static long startOfDayOf(long ms) {
        Calendar cal = Calendar.getInstance();
        cal.setTimeInMillis(ms);
        cal.set(Calendar.HOUR_OF_DAY, 0);
        cal.set(Calendar.MINUTE, 0);
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        return cal.getTimeInMillis();
    }

    /** The shape the cloud stores: {apps:[[name,cat,secs]], hours:[{cat:secs}x24], total, unlocks}. */
    static JSONObject payload(Day d) throws Exception {
        JSONObject o = new JSONObject();
        JSONArray apps = new JSONArray();
        for (App a : d.apps) {
            long s = a.ms / 1000;
            if (s < 1) continue;
            apps.put(new JSONArray().put(a.name).put(a.cat).put(s));
        }
        JSONArray hours = new JSONArray();
        for (int i = 0; i < 24; i++) {
            JSONObject h = new JSONObject();
            for (Map.Entry<String, Long> en : d.hours[i].entrySet()) if (en.getValue() >= 1000) h.put(en.getKey(), en.getValue() / 1000);
            hours.put(h);
        }
        o.put("apps", apps).put("hours", hours).put("total", d.totalMs / 1000).put("unlocks", d.unlocks);
        return o;
    }
}
