package app.hush.phone;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.os.Build;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.URL;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Talks to hush. on the laptop and keeps the shared state in SharedPreferences. */
final class Link {
    static final int PORT = 47322;

    /** Never blockable, whatever is ticked. */
    static final Set<String> ALWAYS_ALLOWED = new HashSet<>(Arrays.asList(
            "com.whatsapp", "com.whatsapp.w4b",
            "org.telegram.messenger", "org.telegram.messenger.web", "org.telegram.plus", "org.thunderdog.challegram",
            "com.discord",
            "app.hush.phone", "com.android.systemui", "com.android.settings", "com.miui.securitycenter",
            "com.android.phone", "com.android.dialer", "com.google.android.dialer", "com.android.incallui",
            "com.android.contacts", "com.google.android.contacts", "com.android.mms", "com.google.android.apps.messaging",
            "com.android.emergency", "com.google.android.inputmethod.latin", "com.android.permissioncontroller",
            "com.google.android.permissioncontroller", "com.android.packageinstaller", "com.miui.packageinstaller"));

    /** Ticked by default if installed. */
    static final List<String> DEFAULT_BLOCKED = Arrays.asList(
            "com.instagram.android", "com.instagram.barcelona", "com.zhiliaoapp.musically", "com.ss.android.ugc.trill",
            "com.snapchat.android", "com.facebook.katana", "com.twitter.android", "com.reddit.frontpage", "com.pinterest");

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("hush", Context.MODE_PRIVATE);
    }

    static Set<String> blocked(Context c) {
        SharedPreferences p = prefs(c);
        if (!p.contains("blocked")) return new HashSet<>(DEFAULT_BLOCKED);
        return new HashSet<>(p.getStringSet("blocked", new HashSet<String>()));
    }

    static void setBlocked(Context c, Set<String> s) {
        prefs(c).edit().putStringSet("blocked", new HashSet<>(s)).apply();
    }

    /** Wall-clock ms until which the phone blocks. Survives the laptop going quiet mid-session. */
    static long blockUntil(Context c) {
        return prefs(c).getLong("blockUntil", 0);
    }

    static boolean blockingNow(Context c) {
        return System.currentTimeMillis() < blockUntil(c);
    }

    static String device() {
        return (Build.MANUFACTURER + " " + Build.MODEL).trim();
    }

    // ---------- HTTP ----------
    static final class Resp {
        int code;
        JSONObject json;
    }

    static Resp http(String host, String method, String path, String code, String body, int timeoutMs) throws Exception {
        URL u = new URL("http://" + host + ":" + PORT + path);
        HttpURLConnection h = (HttpURLConnection) u.openConnection();
        h.setConnectTimeout(timeoutMs);
        h.setReadTimeout(timeoutMs);
        h.setRequestMethod(method);
        h.setUseCaches(false);
        if (code != null) h.setRequestProperty("X-Hush-Code", code);
        h.setRequestProperty("X-Hush-Device", device());
        if (body != null) {
            byte[] b = body.getBytes("UTF-8");
            h.setDoOutput(true);
            h.setRequestProperty("Content-Type", "application/json");
            h.setFixedLengthStreamingMode(b.length);
            OutputStream os = h.getOutputStream();
            os.write(b);
            os.close();
        }
        Resp r = new Resp();
        r.code = h.getResponseCode();
        InputStream in = r.code < 400 ? h.getInputStream() : h.getErrorStream();
        if (in != null) {
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[2048];
            int n;
            while ((n = in.read(buf)) > 0 && bo.size() < 65536) bo.write(buf, 0, n);
            in.close();
            try {
                r.json = new JSONObject(bo.toString("UTF-8"));
            } catch (Exception ignored) {
            }
        }
        h.disconnect();
        return r;
    }

    // ---------- polling ----------
    /** Result of one poll, for the UI. */
    static final int OK = 0, NO_CODE = 1, WRONG_CODE = 2, UNREACHABLE = 3;

    /**
     * Asks the laptop for its state and updates blockUntil. Called every few seconds by the service.
     * If the laptop can't be reached, blockUntil is left alone, so turning Wi-Fi off doesn't end a session early.
     */
    static int poll(Context c) {
        SharedPreferences p = prefs(c);
        String code = p.getString("code", "");
        if (code.isEmpty()) return NO_CODE;
        String host = p.getString("host", "");
        int fails = p.getInt("fails", 0);
        Resp r = null;
        if (!host.isEmpty()) {
            try {
                r = http(host, "GET", "/state", code, null, 2500);
            } catch (Exception e) {
                r = null;
            }
        }
        long now0 = System.currentTimeMillis();
        if (r == null && (host.isEmpty() || fails >= 2) && onWifi(c) && now0 - p.getLong("lastScan", 0) > 60000) {
            // laptop IP probably changed (DHCP): look for it on this Wi-Fi (at most once a minute, never on mobile data)
            p.edit().putLong("lastScan", now0).apply();
            String found = find(c, code, p.getString("laptopId", ""));
            if (found != null) {
                host = found;
                p.edit().putString("host", host).apply();
                try {
                    r = http(host, "GET", "/state", code, null, 2500);
                } catch (Exception e) {
                    r = null;
                }
            }
        }
        if (r == null) {
            p.edit().putInt("fails", fails + 1).apply();
            // away from home Wi-Fi: ask the cloud instead (every 30 s at most)
            int viaCloud = cloudFocus(c, p);
            if (viaCloud == OK) return OK_CLOUD;
            p.edit().putInt("status", UNREACHABLE).apply();
            return UNREACHABLE;
        }
        if (r.code == 403) {
            p.edit().putInt("fails", 0).putInt("status", WRONG_CODE).apply();
            return WRONG_CODE;
        }
        if (r.code != 200 || r.json == null) {
            p.edit().putInt("fails", fails + 1).putInt("status", UNREACHABLE).apply();
            return UNREACHABLE;
        }
        JSONObject j = r.json;
        long now = System.currentTimeMillis();
        applyFocus(p, j);
        p.edit().putLong("lastOk", now).putInt("fails", 0).putInt("status", OK)
                .putString("laptopId", j.optString("id", p.getString("laptopId", ""))).apply();
        // first time on Wi-Fi with a laptop that has cloud sync: pick up the sync address + key
        if (j.optBoolean("cloud", false) && !Cloud.configured(c) && now - p.getLong("cfgTry", 0) > 600000) {
            p.edit().putLong("cfgTry", now).apply();
            Cloud.fetchConfig(c);
        }
        return OK;
    }

    static final int OK_CLOUD = 4;

    private static void applyFocus(SharedPreferences p, JSONObject j) {
        boolean focus = j.optBoolean("focus", false);
        boolean paused = j.optBoolean("paused", false);
        double left = j.optDouble("left", 0);
        long until = 0;
        if (focus) {
            long ms = (long) (left * 1000);
            // paused focus still blocks on the laptop; if we lose contact while paused, give up after 15 min
            if (paused) ms = Math.min(ms, 15 * 60 * 1000L);
            until = System.currentTimeMillis() + Math.max(ms, 5000);
        }
        p.edit().putLong("blockUntil", until).putString("label", j.optString("label", "")).putBoolean("paused", paused).apply();
    }

    /** Focus state from the cloud. Returns OK if it answered; otherwise leaves blockUntil alone. */
    private static int cloudFocus(Context c, SharedPreferences p) {
        if (!Cloud.configured(c)) return UNREACHABLE;
        long now = System.currentTimeMillis();
        if (now - p.getLong("cloudFocusAt", 0) < 30000) return p.getInt("status", UNREACHABLE) == OK_CLOUD ? OK : UNREACHABLE;
        p.edit().putLong("cloudFocusAt", now).apply();
        try {
            JSONObject j = Cloud.focus(c);
            applyFocus(p, j);
            p.edit().putLong("lastCloud", now).putInt("status", OK_CLOUD).apply();
            return OK;
        } catch (Exception e) {
            return UNREACHABLE;
        }
    }

    static boolean onWifi(Context c) {
        try {
            ConnectivityManager cm = (ConnectivityManager) c.getSystemService(Context.CONNECTIVITY_SERVICE);
            android.net.NetworkCapabilities nc = cm.getNetworkCapabilities(cm.getActiveNetwork());
            return nc != null && (nc.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI)
                    || nc.hasTransport(android.net.NetworkCapabilities.TRANSPORT_ETHERNET));
        } catch (Exception e) {
            return true;
        }
    }

    static void reportBlocked(Context c, String appLabel) {
        SharedPreferences p = prefs(c);
        String host = p.getString("host", ""), code = p.getString("code", "");
        if (host.isEmpty() || code.isEmpty()) return;
        try {
            http(host, "POST", "/blocked", code, new JSONObject().put("app", appLabel).toString(), 2500);
        } catch (Exception ignored) {
        }
    }

    // ---------- discovery ----------
    /** This phone's IPv4 address on the current network, or null. */
    static Inet4Address myAddress(Context c) {
        try {
            ConnectivityManager cm = (ConnectivityManager) c.getSystemService(Context.CONNECTIVITY_SERVICE);
            Network n = cm.getActiveNetwork();
            if (n == null) return null;
            LinkProperties lp = cm.getLinkProperties(n);
            if (lp == null) return null;
            for (LinkAddress la : lp.getLinkAddresses()) {
                InetAddress a = la.getAddress();
                if (a instanceof Inet4Address && !a.isLoopbackAddress()) return (Inet4Address) a;
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    /**
     * Scans this Wi-Fi's /24 for hush. Prefers the laptop we paired with (laptopId); otherwise the first one
     * that accepts our code. Returns its IP, or null.
     */
    static String find(Context c, final String code, final String laptopId) {
        Inet4Address me = myAddress(c);
        if (me == null) return null;
        byte[] b = me.getAddress();
        final String prefix = (b[0] & 255) + "." + (b[1] & 255) + "." + (b[2] & 255) + ".";
        final AtomicReference<String> hit = new AtomicReference<>();
        ExecutorService ex = Executors.newFixedThreadPool(48);
        List<Future<?>> fs = new ArrayList<>();
        for (int i = 1; i < 255; i++) {
            final String ip = prefix + i;
            fs.add(ex.submit(new Runnable() {
                public void run() {
                    if (hit.get() != null) return;
                    try {
                        Resp ping = http(ip, "GET", "/ping", null, null, 700);
                        if (ping.code != 200 || ping.json == null || !"hush".equals(ping.json.optString("app"))) return;
                        if (!laptopId.isEmpty() && laptopId.equals(ping.json.optString("id"))) {
                            hit.set(ip);
                            return;
                        }
                        Resp st = http(ip, "GET", "/state", code, null, 1500);
                        if (st.code == 200) hit.compareAndSet(null, ip);
                    } catch (Exception ignored) {
                    }
                }
            }));
        }
        ex.shutdown();
        try {
            ex.awaitTermination(12, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }
        ex.shutdownNow();
        return hit.get();
    }
}
