"""hush. — focus timer + screen time tracker for Windows.

Run:  pythonw app.py          (window)
      pythonw app.py --tray   (start hidden in the tray, used by "Start with Windows")
"""
import logging
import os
import sys
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from core import win  # noqa: E402
from core.db import DB  # noqa: E402
from core.hub import Hub  # noqa: E402
from core.focus import FocusEngine  # noqa: E402
from core.blocker import Blocker  # noqa: E402
from core.bridge import Bridge  # noqa: E402
from core.phonelink import PhoneLink  # noqa: E402
from core.tracker import Tracker  # noqa: E402
from core.api import Api, DEFAULT_SETTINGS  # noqa: E402
from core.names import DEFAULT_CATS  # noqa: E402
from core.tray import Tray  # noqa: E402
from core.icons import IconCache  # noqa: E402

ICO = os.path.join(BASE, "assets", "icon.ico")


def main():
    data = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "hush")
    os.makedirs(data, exist_ok=True)
    logging.basicConfig(filename=os.path.join(data, "hush.log"), level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log = logging.getLogger("hush")

    # single instance: if one is running, ask it to show itself and exit
    if Bridge.ping_existing():
        return

    win.set_app_id()  # own taskbar identity -> our icon instead of Python's
    # let sound effects play even before the first click (e.g. break chime while hidden in the tray)
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "") +
                                                          " --autoplay-policy=no-user-gesture-required --disable-background-timer-throttling"
                                                          " --disable-renderer-backgrounding --disable-backgrounding-occluded-windows").strip()
    import webview  # imported late so the second-instance path stays fast

    start_hidden = "--tray" in sys.argv
    db = DB(os.path.join(data, "hush.db"))
    hub = Hub()
    engine = FocusEngine(db, hub)
    blocker = Blocker(db, engine, hub)
    if not engine.blocking_active():
        blocker.cleanup()  # crash-safety: never leave sites blocked after a crash

    cat_cache = {"t": 0, "map": {}}

    def categorize(app, exe, site):
        if time.time() - cat_cache["t"] > 5:
            cat_cache.update(t=time.time(), map=db.categories())
        over = cat_cache["map"]
        if site:
            if site in over:
                return over[site]
            if site in DEFAULT_CATS:
                return DEFAULT_CATS[site]
            parent = ".".join(site.split(".")[-2:])
            return over.get(parent) or DEFAULT_CATS.get(parent) or "Browsing"
        if app in over:
            return over[app]
        if app in DEFAULT_CATS:
            return DEFAULT_CATS[app]
        return "Games" if blocker.is_game_exe(exe) else "Other"

    def settings():
        s = dict(DEFAULT_SETTINGS)
        s.update(db.get("settings", {}) or {})
        return s

    W = {"main": None, "mini": None, "quitting": False, "mini_shown": None}
    mini_lock = threading.Lock()

    def sync_mini():
        """Mini pill is visible only while a session runs AND the main window is hidden/minimized."""
        if not W["mini"]:
            return
        want = (not hub.ui_visible) and engine.state()["phase"] != "idle"
        with mini_lock:
            if want == W["mini_shown"]:
                return
            W["mini_shown"] = want
            try:
                if want:
                    W["mini"].show()
                    win.round_corners("hush. mini")
                else:
                    W["mini"].hide()
            except Exception:
                pass

    def show_main():
        hub.ui_visible = True
        sync_mini()
        if W["main"]:
            W["main"].show()
            W["main"].restore()

    def hide_main():
        hub.ui_visible = False
        if W["main"]:
            W["main"].hide()
        maybe_mini()

    def maybe_mini():
        sync_mini()

    def can_quit():
        st = engine.state()
        return not (st["mode"] == "hard" and st["phase"] != "idle")

    def quit_app(force=False):
        if not force and not can_quit():
            hub.notify("Hard mode is on. hush. stays until the cycle ends.", "block", system=True)
            return
        W["quitting"] = True
        try:
            tracker.flush()
            blocker.cleanup()
        except Exception:
            log.exception("cleanup")
        tray.stop()
        for k in ("mini", "main"):
            try:
                if W[k]:
                    W[k].destroy()
            except Exception:
                pass

    def toggle():
        st = engine.state()
        if st["phase"] == "idle":
            fm, bm, n = settings()["last_preset"]
            engine.start(st["label"], fm, bm, n, settings()["last_mode"])
            hub.notify(f"Focus started · {fm} min", "info", system=True)
        elif st["paused"]:
            engine.resume()
        else:
            r = engine.pause()
            if not r.get("ok") and r.get("error"):
                hub.notify(r["error"], "block", system=True)

    def toggle_label():
        st = engine.state()
        if st["phase"] == "idle":
            return "Start focus"
        return "Resume" if st["paused"] else "Pause"

    bridge = Bridge(engine, blocker, hub, show_main)
    if not bridge.start():
        log.warning("bridge port busy; extension features disabled")
    phone = PhoneLink(db, engine, hub, os.path.join(BASE, "phone", "hush.apk"))
    phone.start()
    tracker = Tracker(db, engine, blocker, bridge, settings, categorize)
    tray = Tray(show_main, toggle, quit_app, can_quit, toggle_label)
    hub.tray = tray

    SOUNDS = {"block": "block", "break": "break", "success": "complete", "start": "start"}

    def play_hidden(kind):
        """When the window is hidden, phase chimes are played by Python (the webview may be asleep)."""
        if hub.ui_visible or not win.IS_WIN or not settings().get("sfx", True):
            return
        name = SOUNDS.get(kind)
        if not name:
            return
        try:
            import winsound
            winsound.PlaySound(os.path.join(BASE, "ui", "sounds", name + ".wav"), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass

    hub.on_notify = play_hidden

    def on_phase(what):
        if what == "idle":
            sync_mini()
            if not hub.ui_visible:
                show_main()  # show the session summary
        elif what in ("focus", "break"):
            maybe_mini()
            if what == "focus":
                play_hidden("start")

    engine.listeners.append(on_phase)

    icons = IconCache(db, data)
    ctx = {"icons": icons, "ico": ICO, "db": db, "engine": engine, "blocker": blocker, "bridge": bridge, "phone": phone, "hub": hub, "tracker": tracker,
           "categorize": categorize, "script": os.path.join(BASE, "app.py"), "base": BASE,
           "show_main": show_main, "hide_main": hide_main, "quit": quit_app}
    api = Api(ctx)

    ui = lambda f: os.path.join(BASE, "ui", f)  # noqa: E731
    main_win = webview.create_window("hush.", ui("index.html"), js_api=api, width=1140, height=760,
                                     min_size=(960, 660), background_color="#F3EFE7", hidden=start_hidden)
    mini_win = webview.create_window("hush. mini", ui("mini.html"), js_api=api, width=250, height=64,
                                     frameless=True, on_top=True, hidden=True, resizable=False, easy_drag=True,
                                     background_color="#F3EFE7")
    W["main"], W["mini"] = main_win, mini_win
    hub.ui_visible = not start_hidden

    def on_closing():
        if W["quitting"]:
            return True
        threading.Thread(target=hide_main, daemon=True).start()
        return False  # keep running in the tray

    def on_minimized():
        hub.ui_visible = False
        maybe_mini()

    def on_restored():
        hub.ui_visible = True
        sync_mini()

    main_win.events.closing += on_closing
    main_win.events.minimized += on_minimized
    main_win.events.restored += on_restored

    def background():
        try:
            scr = webview.screens[0]
            mini_win.move(scr.width - 270, scr.height - 130)
        except Exception:
            pass
        sync_mini()  # force the pill hidden at launch
        win.set_window_icons(ICO)
        if not db.get("shortcuts_v1"):
            if win.create_shortcuts(os.path.join(BASE, "app.py"), ICO):
                db.set("shortcuts_v1", True)
                hub.notify("Added hush. to your desktop and Start menu", "info")
        tracker.start()
        blocker.start()
        tray.start()
        win.start_hotkey(toggle)
        if start_hidden and engine.state()["phase"] != "idle":
            maybe_mini()
        n = 0
        last_title = None
        while not W["quitting"]:
            sync_mini()
            st = engine.state()
            if st["phase"] == "idle":
                title = "hush."
            else:
                m, sec = divmod(int(st["left"] + 0.999), 60)
                title = f"{m:02d}:{sec:02d} · {'paused' if st['paused'] else st['phase']} · hush."
            if title != last_title:
                last_title = title
                try:
                    main_win.set_title(title)
                except Exception:
                    pass
            if n % 20 == 3:
                win.set_window_icons(ICO)  # re-apply in case Windows reset it after show/hide
            if n % 4 == 0:
                try:
                    tray.update(engine.state())
                except Exception:
                    pass
            n += 1
            time.sleep(0.5)

    webview.start(lambda: threading.Thread(target=background, daemon=True).start(),
                  storage_path=os.path.join(data, "webview"), private_mode=False)
    try:
        tracker.flush()
        blocker.cleanup()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
