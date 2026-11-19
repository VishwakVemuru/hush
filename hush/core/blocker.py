"""Closes blocked apps during focus and manages the site blocklist (hosts file + browser extension)."""
import logging
import os
import threading
import time

import psutil

from . import win
from .names import LAUNCHERS, SUGGESTED_OFF, DEFAULT_SITES, PROTECTED, DISTRACTING, pretty, site_key

log = logging.getLogger("hush.blocker")


class Blocker(threading.Thread):
    def __init__(self, db, engine, hub):
        super().__init__(daemon=True, name="blocker")
        self.db, self.engine, self.hub = db, engine, hub
        self.lock = threading.RLock()
        self.cfg = self._load()
        self._was_active = False
        self._last_kill = {}
        self._warned = False
        self.refresh_games()

    # ---------- config ----------
    def _load(self):
        cfg = self.db.get("blocklist")
        if not cfg:
            apps = [{"id": "exe:" + e, "kind": "exe", "value": e, "name": n, "source": "launcher", "enabled": True}
                    for e, n in LAUNCHERS]
            apps += [{"id": "exe:" + e, "kind": "exe", "value": e, "name": n, "source": "custom", "enabled": False}
                     for e, n in SUGGESTED_OFF]
            cfg = {"apps": apps, "sites": [{"domain": d, "enabled": on} for d, on in DEFAULT_SITES],
                   "shorts": True, "hosts": True}
        return cfg

    def _save(self):
        self.db.set("blocklist", self.cfg)

    def refresh_games(self):
        found = win.detect_games()
        with self.lock:
            old = {a["id"]: a for a in self.cfg["apps"]}
            keep = [a for a in self.cfg["apps"] if a["source"] != "game"]
            for g in found:
                gid = "path:" + g["id"]
                keep.append({"id": gid, "kind": "path", "value": g["path"], "name": g["name"],
                             "source": "game", "store": g["source"],
                             "enabled": old.get(gid, {}).get("enabled", True)})
            self.cfg["apps"] = keep
            self._save()
        return len(found)

    def config(self):
        with self.lock:
            return {"apps": list(self.cfg["apps"]), "sites": list(self.cfg["sites"]),
                    "shorts": self.cfg.get("shorts", True), "hosts": self.cfg.get("hosts", True),
                    "admin": win.is_admin()}

    def set_app(self, aid, enabled):
        with self.lock:
            for a in self.cfg["apps"]:
                if a["id"] == aid:
                    a["enabled"] = bool(enabled)
            self._save()

    def set_source(self, source, enabled):
        with self.lock:
            for a in self.cfg["apps"]:
                if a["source"] == source:
                    a["enabled"] = bool(enabled)
            self._save()

    def add_app(self, exe):
        exe = os.path.basename((exe or "").strip().strip('"')).lower()
        if not exe:
            return False
        if win.IS_WIN and not exe.endswith(".exe"):
            exe += ".exe"  # macOS process names have no extension
        if exe in PROTECTED:
            return False
        with self.lock:
            if any(a["id"] == "exe:" + exe for a in self.cfg["apps"]):
                self.set_app("exe:" + exe, True)
                return True
            self.cfg["apps"].append({"id": "exe:" + exe, "kind": "exe", "value": exe, "name": pretty(exe),
                                     "source": "custom", "enabled": True})
            self._save()
        return True

    def remove_app(self, aid):
        with self.lock:
            self.cfg["apps"] = [a for a in self.cfg["apps"] if not (a["id"] == aid and a["source"] == "custom")]
            self._save()

    def add_site(self, domain):
        d = (domain or "").strip().lower()
        for pre in ("https://", "http://"):
            if d.startswith(pre):
                d = d[len(pre):]
        d = d.split("/")[0].split(":")[0]
        if d.startswith("www."):
            d = d[4:]
        if "." not in d:
            return False
        with self.lock:
            for s in self.cfg["sites"]:
                if s["domain"] == d:
                    s["enabled"] = True
                    break
            else:
                self.cfg["sites"].insert(0, {"domain": d, "enabled": True})
            self._save()
        self._sync_hosts(force=True)
        return True

    def set_site(self, domain, enabled):
        with self.lock:
            for s in self.cfg["sites"]:
                if s["domain"] == domain:
                    s["enabled"] = bool(enabled)
            self._save()
        self._sync_hosts(force=True)

    def remove_site(self, domain):
        with self.lock:
            self.cfg["sites"] = [s for s in self.cfg["sites"] if s["domain"] != domain]
            self._save()
        self._sync_hosts(force=True)

    def set_flag(self, key, value):
        with self.lock:
            self.cfg[key] = bool(value)
            self._save()
        self._sync_hosts(force=True)

    def enabled_sites(self):
        with self.lock:
            return [s["domain"] for s in self.cfg["sites"] if s["enabled"]]

    def shorts(self):
        return bool(self.cfg.get("shorts", True))

    # ---------- matching ----------
    def _rules(self):
        with self.lock:
            names = {a["value"].lower(): a["name"] for a in self.cfg["apps"] if a["enabled"] and a["kind"] == "exe"}
            paths = [(a["value"].lower().rstrip("\\") + "\\", a["name"]) for a in self.cfg["apps"]
                     if a["enabled"] and a["kind"] == "path"]
        return names, paths

    def match(self, name, exe, rules=None):
        names, paths = rules or self._rules()
        n = (name or "").lower()
        if n in PROTECTED:
            return None
        if n in names:
            return names[n]
        e = (exe or "").lower()
        for p, label in paths:
            if e.startswith(p):
                return label
        return None

    def is_game_exe(self, exe):
        e = (exe or "").lower()
        with self.lock:
            return any(e.startswith(a["value"].lower().rstrip("\\") + "\\")
                       for a in self.cfg["apps"] if a["kind"] == "path")

    def site_blocked(self, domain):
        if not domain:
            return False
        d = domain.lower()
        return any(d == s or d.endswith("." + s) for s in self.enabled_sites())

    def is_distracting(self, name, exe, site, category):
        if category in DISTRACTING:
            return True
        if site and self.site_blocked(site):
            return True
        return self.match(name, exe) is not None

    # ---------- hosts ----------
    def _sync_hosts(self, force=False):
        active = self.engine.blocking_active()
        if not win.is_admin():
            return
        if active and self.cfg.get("hosts", True):
            win.write_hosts_block(self.enabled_sites())
        elif force or not active:
            win.write_hosts_block([])

    def cleanup(self):
        win.write_hosts_block([])

    # ---------- loop ----------
    def running_blocked(self):
        rules = self._rules()
        hits = []
        me = os.getpid()
        for p in psutil.process_iter(["pid", "name", "exe"]):
            try:
                if p.info["pid"] == me:
                    continue
                label = self.match(p.info["name"], p.info["exe"], rules)
                if label:
                    hits.append((p, label))
            except (psutil.Error, OSError):
                continue
        return hits

    def run(self):
        while True:
            try:
                self._step()
            except Exception:
                log.exception("blocker step failed")
            time.sleep(1)

    def _step(self):
        active = self.engine.blocking_active()
        if active != self._was_active:
            self._was_active = active
            self._warned = False
            self._sync_hosts()
        if not active:
            return
        if self.engine.in_grace():
            if not self._warned:
                self._warned = True
                running = sorted({label for _, label in self.running_blocked()})
                if running:
                    self.hub.notify(f"Save your stuff · closing {', '.join(running[:3])} in 10s", "block", system=True)
            return
        now = time.time()
        for p, label in self.running_blocked():
            try:
                p.kill()
            except (psutil.Error, OSError):
                continue
            if now - self._last_kill.get(label, 0) > 8:
                self._last_kill[label] = now
                self.engine.add_block(label)
                self.hub.notify(f"hush. {label} can wait · {self.engine.minutes_left()} min left", "block", system=True)
