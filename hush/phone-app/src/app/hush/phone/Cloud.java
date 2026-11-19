package app.hush.phone;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Iterator;

/**
 * Sync with the user's own Cloudflare Worker: upload this phone's daily totals, download the laptop's,
 * and read the laptop's focus state when the laptop isn't reachable on Wi-Fi.
 * The address and key come from the laptop over the paired LAN link; they're never built into the app.
 */
final class Cloud {
    /** The shared hush. service. Every request after sign-in carries the account's own session token. */
    static final String DEFAULT_URL = "https://hush-sync.draw-track-racer.workers.dev";

    static String username(Context c) {
        return Link.prefs(c).getString("username", "");
    }

    /** Sign in with a hush. account. Returns null on success, or a message to show. */
    static String login(Context c, String user, String pass) {
        try {
            URL u = new URL(DEFAULT_URL + "/auth/login");
            HttpURLConnection h = (HttpURLConnection) u.openConnection();
            h.setConnectTimeout(8000);
            h.setReadTimeout(10000);
            h.setRequestMethod("POST");
            h.setRequestProperty("Content-Type", "application/json");
            h.setRequestProperty("User-Agent", "hush-phone/1.4");
            byte[] b = new JSONObject().put("username", user).put("password", pass).put("device", "phone").toString().getBytes("UTF-8");
            h.setDoOutput(true);
            h.setFixedLengthStreamingMode(b.length);
            OutputStream os = h.getOutputStream();
            os.write(b);
            os.close();
            int code = h.getResponseCode();
            InputStream in = code < 400 ? h.getInputStream() : h.getErrorStream();
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            if (in != null) {
                byte[] buf = new byte[4096];
                int n;
                while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
                in.close();
            }
            JSONObject r = new JSONObject(bo.size() > 0 ? bo.toString("UTF-8") : "{}");
            if (code != 200) return r.optString("error", "Couldn't sign in (" + code + ")");
            Link.prefs(c).edit().putString("cloudUrl", DEFAULT_URL).putString("cloudKey", r.getString("token"))
                    .putString("username", r.getJSONObject("user").optString("username"))
                    .putLong("laptopSince", 0).apply();
            return null;
        } catch (Exception e) {
            return "Can't reach the hush. server. Check your internet.";
        }
    }

    static void logout(Context c) {
        try {
            if (!username(c).isEmpty()) req(c, "POST", "/auth/logout", new JSONObject());
        } catch (Exception ignored) {
        }
        Link.prefs(c).edit().remove("cloudUrl").remove("cloudKey").remove("username").apply();
    }

    /** Friends leaderboard for today / this week, in this phone's timezone. */
    static JSONObject leaderboard(Context c, boolean week) throws Exception {
        java.util.Calendar start = Usage.startOfDay(week ? 6 : 0);
        int tz = java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000;
        return req(c, "GET", "/leaderboard?from=" + start.getTimeInMillis() + "&tz=" + tz, null);
    }

    static boolean configured(Context c) {
        SharedPreferences p = Link.prefs(c);
        return !p.getString("cloudUrl", "").isEmpty() && !p.getString("cloudKey", "").isEmpty();
    }

    static JSONObject req(Context c, String method, String path, JSONObject body) throws Exception {
        SharedPreferences p = Link.prefs(c);
        URL u = new URL(p.getString("cloudUrl", "") + path);
        if (!"https".equals(u.getProtocol())) throw new IllegalStateException("cloud must be https");
        HttpURLConnection h = (HttpURLConnection) u.openConnection();
        h.setConnectTimeout(8000);
        h.setReadTimeout(10000);
        h.setRequestMethod(method);
        h.setRequestProperty("Authorization", "Bearer " + p.getString("cloudKey", ""));
        h.setRequestProperty("User-Agent", "hush-phone/1.3");
        if (body != null) {
            byte[] b = body.toString().getBytes("UTF-8");
            h.setDoOutput(true);
            h.setRequestProperty("Content-Type", "application/json");
            h.setFixedLengthStreamingMode(b.length);
            OutputStream os = h.getOutputStream();
            os.write(b);
            os.close();
        }
        int code = h.getResponseCode();
        InputStream in = code < 400 ? h.getInputStream() : h.getErrorStream();
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        if (in != null) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0 && bo.size() < 2_000_000) bo.write(buf, 0, n);
            in.close();
        }
        h.disconnect();
        if (code >= 400) throw new IllegalStateException("cloud " + code);
        return new JSONObject(bo.toString("UTF-8"));
    }

    /** Ask the paired laptop (same Wi-Fi) for the sync address + key. */
    static boolean fetchConfig(Context c) {
        SharedPreferences p = Link.prefs(c);
        String host = p.getString("host", ""), code = p.getString("code", "");
        if (host.isEmpty() || code.isEmpty()) return false;
        try {
            Link.Resp r = Link.http(host, "GET", "/cloud", code, null, 3000);
            if (r.code != 200 || r.json == null) return false;
            String url = r.json.optString("url", ""), key = r.json.optString("key", "");
            if (!url.startsWith("https://") || key.length() < 20) return false;
            p.edit().putString("cloudUrl", url).putString("cloudKey", key).apply();
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /** Upload today's and yesterday's phone totals (only when they changed) and keep a local copy for history. */
    static void pushDays(Context c) throws Exception {
        if (!configured(c) || !Usage.allowed(c)) return;
        SharedPreferences p = Link.prefs(c);
        JSONObject mine = new JSONObject(p.getString("phoneDays", "{}"));
        for (int ago = 1; ago >= 0; ago--) {
            Usage.Day d = Usage.day(c, ago);
            JSONObject data = Usage.payload(d);
            data.put("blocked", p.getInt("blocked_" + d.date, 0));
            String s = data.toString();
            mine.put(d.date, data);
            if (s.equals(p.getString("sent_" + d.date, ""))) continue;
            req(c, "PUT", "/day", new JSONObject().put("device", "phone").put("day", d.date).put("data", data));
            p.edit().putString("sent_" + d.date, s).apply();
        }
        p.edit().putString("phoneDays", trim(mine).toString()).apply();
    }

    /** Download the laptop's daily totals for the Combined tab. */
    static void pullLaptop(Context c) throws Exception {
        if (!configured(c)) return;
        SharedPreferences p = Link.prefs(c);
        long since = p.getLong("laptopSince", 0);
        String from = Usage.iso(Usage.startOfDay(35)), to = Usage.iso(Usage.startOfDay(0));
        JSONObject r = req(c, "GET", "/days?from=" + from + "&to=" + to + "&since=" + since, null);
        JSONObject lap = new JSONObject(p.getString("laptopDays", "{}"));
        JSONArray days = r.optJSONArray("days");
        if (days == null) return;
        for (int i = 0; i < days.length(); i++) {
            JSONObject row = days.getJSONObject(i);
            since = Math.max(since, row.optLong("updated", 0));
            if ("laptop".equals(row.optString("device"))) lap.put(row.getString("day"), row.getJSONObject("data"));
        }
        p.edit().putString("laptopDays", trim(lap).toString()).putLong("laptopSince", since)
                .putLong("cloudOk", System.currentTimeMillis()).apply();
    }

    /** Laptop focus state from the cloud, used only when the laptop isn't on this Wi-Fi. */
    static JSONObject focus(Context c) throws Exception {
        return req(c, "GET", "/focus", null);
    }

    /** Everything the background service does every ~15 minutes. Never throws. */
    static void syncQuietly(Context c) {
        try {
            if (!configured(c) && username(c).isEmpty()) fetchConfig(c);
            pushDays(c);
            pullLaptop(c);
            Link.prefs(c).edit().putLong("lastSync", System.currentTimeMillis()).apply();
        } catch (Exception ignored) {
        }
    }

    private static JSONObject trim(JSONObject o) {
        // keep ~45 days
        String cutoff = Usage.iso(Usage.startOfDay(45));
        JSONObject out = new JSONObject();
        for (Iterator<String> it = o.keys(); it.hasNext(); ) {
            String k = it.next();
            if (k.compareTo(cutoff) >= 0) {
                try {
                    out.put(k, o.get(k));
                } catch (Exception ignored) {
                }
            }
        }
        return out;
    }
}
