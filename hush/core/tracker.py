"""Samples the foreground app every second and stores usage chunks."""
import logging
import threading
import time

import psutil

from . import win
from .names import BROWSERS, pretty, site_key

log = logging.getLogger("hush.tracker")
SKIP = {"lockapp.exe", "logonui.exe", "screensaver.exe", "loginwindow", "screensaverengine"}


class Tracker(threading.Thread):
    def __init__(self, db, engine, blocker, bridge, settings, categorize):
        super().__init__(daemon=True, name="tracker")
        self.db, self.engine, self.blocker, self.bridge = db, engine, blocker, bridge
        self.settings = settings
        self.categorize = categorize
        self.cur = None
        self.now_using = None
        self._pcache = {}

    def _proc(self, pid):
        hit = self._pcache.get(pid)
        if hit:
            return hit
        try:
            p = psutil.Process(pid)
            info = (p.name(), p.exe())
        except (psutil.Error, OSError):
            try:
                info = (psutil.Process(pid).name(), "")
            except (psutil.Error, OSError):
                return None, None
        if len(self._pcache) > 500:
            self._pcache.clear()
        self._pcache[pid] = info
        return info

    def _sample(self):
        fg = win.foreground()
        if not fg:
            return None
        hwnd, pid, title, cls = fg
        name, exe = self._proc(pid)
        if not name or name.lower() in SKIP:
            return None
        if name.lower() == "explorer.exe" and cls in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return None
        timeout = float(self.settings().get("idle_min", 3)) * 60
        if win.idle_seconds() > timeout and not win.is_fullscreen(hwnd):
            return None
        site = None
        if name.lower() in BROWSERS:
            a = self.bridge.activity()
            if a and time.time() - a["ts"] < 25:
                site = site_key(a["domain"])
        return pretty(name), exe, site, title

    def _close(self):
        if self.cur:
            self.db.usage_update(self.cur["id"], self.cur["end"], self.cur["title"])
            self.cur = None

    def step(self):
        now = time.time()
        info = self._sample()
        if info is None:
            self._close()
            self.now_using = None
            return
        app, exe, site, title = info
        # The live site only feeds the focus score (e.g. a blocked site counts as distracted).
        # Screen time itself records just the browser, never which websites were open.
        self.engine.on_second(self.blocker.is_distracting(app, exe, site, self.categorize(app, exe, site)) and app != "hush.")
        site = None
        cat = self.categorize(app, exe, None)
        self.now_using = {"app": app, "site": None, "category": cat}
        key = (app, None)
        if self.cur and self.cur["key"] == key and now - self.cur["end"] <= 5:
            self.cur["end"] = now
            self.cur["title"] = title[:200]
            if now - self.cur["saved"] >= 5:
                self.db.usage_update(self.cur["id"], now, self.cur["title"])
                self.cur["saved"] = now
        else:
            self._close()
            rid = self.db.usage_insert(app, exe, site, title[:200], now - 1, now)
            self.cur = {"id": rid, "key": key, "end": now, "title": title[:200], "saved": now}

    def run(self):
        while True:
            t0 = time.time()
            try:
                self.engine.tick()
                self.engine.tick_second()
                if win.IS_WIN or win.IS_MAC:
                    self.step()
            except Exception:
                log.exception("tracker step failed")
            time.sleep(max(0.05, 1 - (time.time() - t0)))

    def flush(self):
        self._close()
