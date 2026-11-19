"""Everything the UI can call (window.pywebview.api.*). Only public methods are exposed."""
import csv
import os
import time
from datetime import datetime

import psutil

from . import win, stats
from .focus import PHRASE
from .names import CATEGORIES, DEFAULT_CATS, CAT_COLORS, pretty

DEFAULT_SETTINGS = {
    "name": "", "goal_hours": 4, "idle_min": 3, "custom_focus": 45, "custom_break": 10,
    "unlock": "both", "countdown_label": "", "countdown_date": "",
    "reduce_motion": False, "volume": 0.5, "last_preset": [50, 10, 4], "last_mode": "soft",
    "doh_off": False, "sfx": True, "sfx_volume": 0.35, "onboarded": False,
    "mini_mode": "minimized",  # "minimized" = floating mini timer only when the window is minimized; "off" = never
    "camera_check": False,     # on-device study check during focus (face in view, no phone)
}


class Api:
    def __init__(self, ctx):
        self._ctx = ctx  # dict with db, engine, blocker, bridge, hub, tracker, app callbacks

    # ---------- internals ----------
    def _settings(self):
        s = dict(DEFAULT_SETTINGS)
        s.update(self._ctx["db"].get("settings", {}) or {})
        return s

    # ---------- state ----------
    def poll(self, last_event_id=0):
        c = self._ctx
        tr = c.get("tracker")
        return {"state": c["engine"].state(), "events": c["hub"].since(int(last_event_id or 0)),
                "now_using": tr.now_using if tr else None, "ext": c["bridge"].extension_connected()}

    def boot(self):
        c = self._ctx
        return {"settings": self._settings(), "categories": CATEGORIES, "colors": CAT_COLORS,
                "phrase": PHRASE, "admin": win.is_admin(), "startup": win.get_startup(),
                "is_windows": win.IS_WIN, "last_event": c["hub"].last_id(), "version": "1.3"}

    def overview(self):
        return stats.overview(self._ctx["db"], float(self._settings()["goal_hours"]))

    # ---------- focus ----------
    def start_focus(self, opts):
        opts = opts or {}
        s = self._settings()
        s["last_preset"] = [int(opts.get("focus_min", 50)), int(opts.get("break_min", 10)), int(opts.get("sessions", 4))]
        s["last_mode"] = opts.get("mode", "soft")
        self._ctx["db"].set("settings", s)
        return self._ctx["engine"].start(opts.get("label", ""), opts.get("focus_min", 50), opts.get("break_min", 10),
                                         opts.get("sessions", 4), opts.get("mode", "soft"))

    def pause(self):
        return self._ctx["engine"].pause()

    def resume(self):
        return self._ctx["engine"].resume()

    def skip(self):
        return self._ctx["engine"].skip()

    def request_stop(self):
        return self._ctx["engine"].request_stop()

    def stop(self, proof=None):
        return self._ctx["engine"].stop(proof)

    def clear_summary(self):
        self._ctx["engine"].summary = None
        return True

    # ---------- stats ----------
    def stats(self, rng="day", source="laptop", offset=0):
        c = self._ctx
        cloud = c.get("cloud")
        over = c["db"].categories()
        recat = lambda name, cat: over.get(name) or cat  # noqa: E731  (your category edits apply to phone apps too)
        return stats.compute(c["db"], rng, c["categorize"], source,
                             cloud.phone_cache() if cloud else {}, recat, offset)

    def day_totals(self, source="laptop"):
        """Screen time per day for the last 30 days (the day picker on Stats)."""
        c = self._ctx
        cloud = c.get("cloud")
        over = c["db"].categories()
        return stats.day_totals(c["db"], c["categorize"], source, cloud.phone_cache() if cloud else {},
                                lambda name, cat: over.get(name) or cat)

    # ---------- account, friends, leaderboard ----------
    def _cloud_call(self, fn, *a):
        from .cloud import CloudError
        cloud = self._ctx.get("cloud")
        if not cloud:
            return {"error": "Cloud isn't available"}
        try:
            return fn(cloud, *a)
        except CloudError as e:
            return {"error": str(e), "status": e.status}

    def account_status(self):
        cloud = self._ctx.get("cloud")
        return cloud.status() if cloud else {"enabled": False, "signed_in": False}

    def signup(self, username, password, display=""):
        return self._cloud_call(lambda c: c.signup(str(username or ""), str(password or ""), str(display or "")))

    def login(self, username, password):
        return self._cloud_call(lambda c: c.login(str(username or ""), str(password or "")))

    def logout(self):
        return self._cloud_call(lambda c: c.logout())

    def friends(self):
        return self._cloud_call(lambda c: c.friends())

    def add_friend(self, username):
        return self._cloud_call(lambda c: c.add_friend(str(username or "").strip().lstrip("@")))

    def accept_friend(self, username):
        return self._cloud_call(lambda c: c.accept_friend(str(username or "")))

    def remove_friend(self, username):
        return self._cloud_call(lambda c: c.remove_friend(str(username or "")))

    def leaderboard(self, rng="week"):
        return self._cloud_call(lambda c: c.leaderboard(rng if rng in ("day", "week", "month") else "week"))

    def my_week(self):
        """Your last 7 days from local sessions: focus and camera-verified seconds per day (for the Friends band)."""
        from datetime import date, datetime, timedelta
        today = date.today()
        out = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            a = datetime.combine(d, datetime.min.time()).timestamp()
            rows = self._ctx["db"].focus_between(a, a + 86400)
            focus = sum(min(max(0, (r["end"] or 0) - (r["start"] or 0)), (r["planned"] or 0) or 1e9) for r in rows)
            verified = sum(r.get("verified") or 0 for r in rows)
            out.append({"label": "Today" if i == 0 else d.strftime("%a"), "focus": round(focus), "verified": round(min(verified, focus))})
        cam = bool(self._settings().get("camera_check"))
        return {"days": out, "camera": cam}

    # ---------- camera study check ----------
    def presence(self, state):
        """The UI's camera check reports present / away / phone every couple of seconds during focus."""
        self._ctx["engine"].set_presence(str(state or ""))
        return True

    def cloud_status(self):
        cloud = self._ctx.get("cloud")
        return cloud.status() if cloud else {"enabled": False}

    def cloud_refresh(self):
        cloud = self._ctx.get("cloud")
        return {"changed": cloud.refresh(), "status": cloud.status()} if cloud else {"changed": False, "status": {"enabled": False}}

    def save_image(self, data_url, name="hush-screen-time"):
        """Saves a PNG made by the UI (share card) to Downloads and shows it in Explorer."""
        import base64
        import re
        m = re.match(r"^data:image/png;base64,([A-Za-z0-9+/=]+)$", str(data_url or ""))
        if not m:
            return None
        raw = base64.b64decode(m.group(1))
        if len(raw) > 15 * 1024 * 1024:
            return None
        folder = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(folder, exist_ok=True)
        safe = re.sub(r"[^a-z0-9-]+", "-", str(name).lower()).strip("-")[:60] or "hush-screen-time"
        path = os.path.join(folder, f"{safe}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        with open(path, "wb") as f:
            f.write(raw)
        try:
            win.reveal_file(path)
        except Exception:
            pass
        return path

    def set_category(self, name, cat):
        if cat in CATEGORIES:
            self._ctx["db"].set_category(name, cat)
        return True

    def export_csv(self):
        db = self._ctx["db"]
        folder = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        p1 = os.path.join(folder, f"hush-usage-{stamp}.csv")
        p2 = os.path.join(folder, f"hush-focus-{stamp}.csv")
        cat = self._ctx["categorize"]
        with open(p1, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["start", "end", "seconds", "app", "site", "category", "window_title"])
            for r in db.q("SELECT * FROM usage ORDER BY start"):
                w.writerow([datetime.fromtimestamp(r["start"]).isoformat(timespec="seconds"),
                            datetime.fromtimestamp(r["end"]).isoformat(timespec="seconds"),
                            round(r["end"] - r["start"]), r["app"], r["site"] or "", cat(r["app"], r["exe"], r["site"]), r["title"]])
        with open(p2, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["start", "label", "mode", "planned_min", "in_session_min", "distracted_min", "blocked", "completed"])
            for r in db.q("SELECT * FROM focus ORDER BY start"):
                w.writerow([datetime.fromtimestamp(r["start"]).isoformat(timespec="seconds"), r["label"], r["mode"],
                            round((r["planned"] or 0) / 60), round((r["tracked"] or 0) / 60),
                            round((r["distracted"] or 0) / 60), r["blocked"], r["completed"]])
        try:
            win.open_path(folder)
        except Exception:
            pass
        return folder

    # ---------- tasks ----------
    def tasks(self):
        return self._ctx["db"].tasks()

    def add_task(self, text):
        text = (text or "").strip()[:120]
        if text:
            self._ctx["db"].task_add(text)
        return self.tasks()

    def toggle_task(self, tid):
        self._ctx["db"].task_toggle(int(tid))
        return self.tasks()

    def delete_task(self, tid):
        self._ctx["db"].task_delete(int(tid))
        return self.tasks()

    def clear_done(self):
        self._ctx["db"].tasks_clear_done()
        return self.tasks()

    # ---------- blocklist ----------
    def blocklist(self):
        cfg = self._ctx["blocker"].config()
        cfg["ext"] = self._ctx["bridge"].extension_connected()
        return cfg

    def set_app(self, aid, enabled):
        self._ctx["blocker"].set_app(aid, enabled)
        return self.blocklist()

    def set_source(self, source, enabled):
        self._ctx["blocker"].set_source(source, enabled)
        return self.blocklist()

    def add_app(self, exe):
        ok = self._ctx["blocker"].add_app(exe)
        return {"ok": ok, "cfg": self.blocklist()}

    def remove_app(self, aid):
        self._ctx["blocker"].remove_app(aid)
        return self.blocklist()

    def add_site(self, domain):
        ok = self._ctx["blocker"].add_site(domain)
        return {"ok": ok, "cfg": self.blocklist()}

    def set_site(self, domain, enabled):
        self._ctx["blocker"].set_site(domain, enabled)
        return self.blocklist()

    def remove_site(self, domain):
        self._ctx["blocker"].remove_site(domain)
        return self.blocklist()

    def set_block_flag(self, key, value):
        if key in ("shorts", "hosts"):
            self._ctx["blocker"].set_flag(key, value)
        return self.blocklist()

    def rescan_games(self):
        n = self._ctx["blocker"].refresh_games()
        return {"found": n, "cfg": self.blocklist()}

    def running_apps(self):
        seen = {}
        windir = os.environ.get("WINDIR", r"C:\Windows").lower()
        for p in psutil.process_iter(["name", "exe"]):
            try:
                n, e = p.info["name"], (p.info["exe"] or "")
                if not n or not e or e.lower().startswith(windir):
                    continue
                if n.lower() in ("python.exe", "pythonw.exe", "msedgewebview2.exe"):
                    continue
                seen[n.lower()] = {"exe": n, "name": pretty(n)}
            except (psutil.Error, OSError):
                continue
        return sorted(seen.values(), key=lambda x: x["name"].lower())

    # ---------- settings ----------
    def settings(self):
        return self._settings()

    def set_setting(self, key, value):
        if key not in DEFAULT_SETTINGS:
            return False
        s = self._settings()
        s[key] = value
        self._ctx["db"].set("settings", s)
        if key == "mini_mode" and self._ctx.get("sync_mini"):
            self._ctx["sync_mini"]()
        return True

    def close_mini(self):
        f = self._ctx.get("close_mini")
        if f:
            f()
        return True

    def set_fullscreen(self, on):
        f = self._ctx.get("fullscreen")
        return f(bool(on)) if f else False

    def set_startup(self, enabled):
        try:
            return win.set_startup(bool(enabled), self._ctx["script"])
        except OSError:
            return False

    def set_doh(self, disable):
        ok = win.set_doh_policy(bool(disable))
        if ok:
            self.set_setting("doh_off", bool(disable))
        return ok

    def restart_admin(self):
        if win.relaunch_as_admin(self._ctx["script"]):
            self._ctx["quit"](force=True)
            return True
        return False

    def open_extension_folder(self):
        win.open_path(os.path.join(self._ctx["base"], "extension"))
        return True

    # ---------- phone link ----------
    def phone_link(self):
        return self._ctx["phone"].info()

    def phone_new_code(self):
        return self._ctx["phone"].regenerate()

    # ---------- icons & shortcuts ----------
    def app_icons(self, names):
        try:
            return self._ctx["icons"].get(list(names or [])[:60])
        except Exception:
            return {}

    def create_shortcut(self):
        ok = win.create_shortcuts(self._ctx["script"], self._ctx["ico"])
        if ok:
            self._ctx["db"].set("shortcuts_v1", True)
        return ok

    # ---------- windows ----------
    def show_main(self):
        self._ctx["show_main"]()
        return True

    def hide_to_tray(self):
        self._ctx["hide_main"]()
        return True
