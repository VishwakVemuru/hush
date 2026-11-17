package app.hush.phone;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.PowerManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * Mirrors laptop focus sessions: polls hush. on the laptop and sends picked apps home while it's in focus.
 * Any error fails open (nothing gets blocked), so a bug can never lock the phone.
 */
public class BlockService extends AccessibilityService {
    static volatile boolean running = false;

    private Handler main;
    private Handler net;
    private HandlerThread netThread;
    private final Set<String> homes = new HashSet<>();
    private final Map<String, Long> lastReport = new HashMap<>();
    private volatile String front = "";
    private long lastKick = 0;

    @Override
    protected void onServiceConnected() {
        running = true;
        main = new Handler(Looper.getMainLooper());
        netThread = new HandlerThread("hush-net");
        netThread.start();
        net = new Handler(netThread.getLooper());
        loadHomes();
        net.post(pollLoop);
        main.postDelayed(checkLoop, 1500);
    }

    private void loadHomes() {
        try {
            Intent i = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
            for (ResolveInfo r : getPackageManager().queryIntentActivities(i, PackageManager.MATCH_ALL)) {
                homes.add(r.activityInfo.packageName);
            }
        } catch (Exception ignored) {
        }
    }

    private boolean screenOn() {
        try {
            return ((PowerManager) getSystemService(Context.POWER_SERVICE)).isInteractive();
        } catch (Exception e) {
            return true;
        }
    }

    /** Ask the laptop every 4 s while the screen is on (every 30 s when it's off). */
    private final Runnable pollLoop = new Runnable() {
        public void run() {
            try {
                boolean wasBlocking = Link.blockingNow(BlockService.this);
                Link.poll(BlockService.this);
                if (!wasBlocking && Link.blockingNow(BlockService.this)) main.post(checkNow);
            } catch (Exception ignored) {
            }
            // screen-time sync with the cloud: every 15 min while the phone is in use
            long now = System.currentTimeMillis();
            if (now - Link.prefs(BlockService.this).getLong("lastSyncTry", 0) > 15 * 60000L && screenOn()) {
                Link.prefs(BlockService.this).edit().putLong("lastSyncTry", now).apply();
                Cloud.syncQuietly(BlockService.this);
            }
            if (running) net.postDelayed(this, screenOn() ? 4000 : 30000);
        }
    };

    /** Catches apps that were already open when a session starts, not just ones opened afterwards. */
    private final Runnable checkLoop = new Runnable() {
        public void run() {
            checkNow.run();
            if (running) main.postDelayed(this, Link.blockingNow(BlockService.this) ? 1500 : 5000);
        }
    };

    private final Runnable checkNow = new Runnable() {
        public void run() {
            try {
                if (!screenOn() || !Link.blockingNow(BlockService.this)) return;
                String pkg = currentPackage();
                if (pkg != null) maybeBlock(pkg);
            } catch (Exception ignored) {
            }
        }
    };

    private String currentPackage() {
        try {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root != null && root.getPackageName() != null) {
                String p = root.getPackageName().toString();
                root.recycle();
                return p;
            }
        } catch (Exception ignored) {
        }
        return front.isEmpty() ? null : front;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent e) {
        try {
            if (e == null || e.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED || e.getPackageName() == null) return;
            String pkg = e.getPackageName().toString();
            front = pkg;
            if (Link.blockingNow(this)) maybeBlock(pkg);
        } catch (Exception ignored) {
        }
    }

    private void maybeBlock(String pkg) {
        if (pkg.equals(getPackageName()) || Link.ALWAYS_ALLOWED.contains(pkg) || homes.contains(pkg)) return;
        if (!Link.blocked(this).contains(pkg)) return;
        long now = System.currentTimeMillis();
        if (now - lastKick < 700) return;
        lastKick = now;
        performGlobalAction(GLOBAL_ACTION_HOME);
        final String label = label(pkg);
        try {
            // HyperOS often blocks the full-screen page from the background, so always show a toast too
            long ms = Link.blockUntil(this) - now;
            android.widget.Toast.makeText(this, "hush. " + label + " can wait · " + Math.max(1, (ms + 59999) / 60000) + " min of focus left",
                    android.widget.Toast.LENGTH_LONG).show();
        } catch (Exception ignored) {
        }
        try {
            Intent i = new Intent(this, BlockedActivity.class)
                    .putExtra("app", label)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            startActivity(i);
        } catch (Exception ignored) {
        }
        try {
            String key = "blocked_" + Usage.iso(Usage.startOfDay(0));
            Link.prefs(this).edit().putInt(key, Link.prefs(this).getInt(key, 0) + 1).apply();
        } catch (Exception ignored) {
        }
        Long last = lastReport.get(pkg);
        if (last == null || now - last > 60000) {
            lastReport.put(pkg, now);
            net.post(new Runnable() {
                public void run() {
                    Link.reportBlocked(BlockService.this, label);
                }
            });
        }
    }

    private String label(String pkg) {
        try {
            PackageManager pm = getPackageManager();
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (Exception e) {
            return pkg;
        }
    }

    @Override
    public void onInterrupt() {
    }

    @Override
    public void onDestroy() {
        running = false;
        try {
            if (main != null) main.removeCallbacksAndMessages(null);
            if (netThread != null) netThread.quitSafely();
        } catch (Exception ignored) {
        }
        super.onDestroy();
    }
}
