"""macOS versions of the helpers in win.py (imported over them when running on a Mac).

Uses pyobjc (AppKit / Quartz). Anything macOS won't allow without extra permission degrades quietly:
- the global hotkey needs Accessibility permission (System Settings > Privacy & Security > Accessibility)
- the system-wide hosts-file block isn't offered on Mac yet (the browser extension still blocks sites)
"""
import os
import plistlib
import re
import subprocess
import sys
import threading

IS_WIN = False
IS_MAC = True
FROZEN = getattr(sys, "frozen", False)

try:
    from AppKit import NSWorkspace, NSBitmapImageRep, NSPNGFileType  # type: ignore
    import Quartz  # type: ignore
    HAVE_OBJC = True
except Exception:  # pragma: no cover - pyobjc missing
    HAVE_OBJC = False


# ---------- activity ----------
def foreground():
    """(handle, pid, title, class) like the Windows version. On Mac the 'title' is the app name: reading window
    titles needs Screen Recording permission, and screen time only needs the app."""
    if not HAVE_OBJC:
        return None
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    pid = int(app.processIdentifier())
    return pid, pid, str(app.localizedName() or ""), ""


def idle_seconds():
    if not HAVE_OBJC:
        return 0.0
    try:
        return float(Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType))
    except Exception:
        return 0.0


def is_fullscreen(pid):
    """True if the front app has an on-screen window as big as the main display (fullscreen video/game)."""
    if not HAVE_OBJC or not pid:
        return False
    try:
        main = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        wins = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                                                 Quartz.kCGNullWindowID) or []
        for w in wins:
            if int(w.get("kCGWindowOwnerPID", 0)) != pid or int(w.get("kCGWindowLayer", 1)) != 0:
                continue
            b = w.get("kCGWindowBounds") or {}
            if b.get("Width", 0) >= main.size.width and b.get("Height", 0) >= main.size.height:
                return True
    except Exception:
        pass
    return False


# ---------- admin / launching ----------
def is_admin():
    return False  # hush never runs as root on Mac; the hosts-file block isn't offered


def relaunch_as_admin(script):
    return False


def pythonw():
    return sys.executable


def launch_cmd(script):
    if FROZEN:
        # .../hush.app/Contents/MacOS/hush
        return sys.executable, "", os.path.dirname(sys.executable)
    return sys.executable, f'"{script}"', os.path.dirname(script)


AGENT = os.path.expanduser("~/Library/LaunchAgents/app.hush.focus.plist")


def set_startup(enabled, script):
    """Start with macOS via a per-user LaunchAgent."""
    try:
        if enabled:
            exe, _, wd = launch_cmd(script)
            args = [exe, "--tray"] if FROZEN else [exe, script, "--tray"]
            os.makedirs(os.path.dirname(AGENT), exist_ok=True)
            with open(AGENT, "wb") as f:
                plistlib.dump({"Label": "app.hush.focus", "ProgramArguments": args, "RunAtLoad": True,
                               "WorkingDirectory": wd}, f)
        elif os.path.exists(AGENT):
            os.remove(AGENT)
        return True
    except OSError:
        return False


def get_startup():
    return os.path.exists(AGENT)


def set_doh_policy(disable):
    return False


def write_hosts_block(domains):
    return False


# ---------- games ----------
def detect_games():
    games = {}

    def add(path, name, source):
        if os.path.isdir(path):
            games[path.lower()] = {"id": path.lower(), "name": name, "path": path, "source": source}

    steam = os.path.expanduser("~/Library/Application Support/Steam")
    libs = {steam}
    try:
        with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="ignore") as f:
            libs.update(m.group(1) for m in re.finditer(r'"path"\s+"([^"]+)"', f.read()))
    except OSError:
        pass
    for lib in libs:
        common = os.path.join(lib, "steamapps", "common")
        if os.path.isdir(common):
            for d in os.listdir(common):
                if not d.lower().startswith("steamworks"):
                    add(os.path.join(common, d), d, "Steam")
    epic = os.path.expanduser("~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests")
    if os.path.isdir(epic):
        import json
        for item in os.listdir(epic):
            if item.endswith(".item"):
                try:
                    with open(os.path.join(epic, item), encoding="utf-8", errors="ignore") as f:
                        j = json.load(f)
                    add(j.get("InstallLocation", ""), j.get("DisplayName", "Epic game"), "Epic")
                except (OSError, ValueError):
                    pass
    for app in ("Roblox.app", "Minecraft.app", "League of Legends.app"):
        add(os.path.join("/Applications", app), app[:-4], "App")
    return sorted(games.values(), key=lambda g: g["name"].lower())


# ---------- global hotkey: Control+Option+H ----------
def start_hotkey(callback, vk=None):
    if not HAVE_OBJC:
        return

    def loop():
        try:
            KEY_H = 4  # kVK_ANSI_H
            want = Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskAlternate

            def tap(proxy, etype, event, refcon):
                if etype == Quartz.kCGEventKeyDown:
                    code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                    flags = Quartz.CGEventGetFlags(event)
                    if code == KEY_H and (flags & want) == want:
                        threading.Thread(target=callback, daemon=True).start()
                return event

            port = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                           Quartz.kCGEventTapOptionListenOnly,
                                           Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown), tap, None)
            if not port:
                return  # no Accessibility permission: the shortcut just isn't available
            src = Quartz.CFMachPortCreateRunLoopSource(None, port, 0)
            loop_ref = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(loop_ref, src, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(port, True)
            Quartz.CFRunLoopRun()
        except Exception:
            pass

    threading.Thread(target=loop, daemon=True, name="hotkey").start()


# ---------- window chrome (native macOS already looks right) ----------
def round_corners(title):
    pass


def style_caption(*a, **k):
    pass


def set_app_id(app_id=None):
    pass


def own_windows():
    return []


def set_window_icons(ico_path):
    pass


def create_shortcuts(script, ico):
    return True  # the .app lives in Applications / the Dock


# ---------- icons, files ----------
def extract_icons(jobs, tmp_dir):
    """jobs: [{'exe': path, 'out': png}] -> PNG of each app's icon (the .app bundle's icon when there is one)."""
    if not HAVE_OBJC:
        return
    ws = NSWorkspace.sharedWorkspace()
    for j in jobs:
        try:
            path = j["exe"]
            m = re.search(r"^(.*?\.app)/", path or "")
            img = ws.iconForFile_(m.group(1) if m else path)
            img.setSize_((64, 64))
            rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
            data = rep.representationUsingType_properties_(NSPNGFileType, None)
            data.writeToFile_atomically_(j["out"], True)
        except Exception:
            continue


def open_path(path):
    subprocess.Popen(["open", path])


def reveal_file(path):
    if os.path.exists(path):
        subprocess.Popen(["open", "-R", path])


def play_sound(path):
    subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
