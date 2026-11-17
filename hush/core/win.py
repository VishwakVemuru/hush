"""Thin Windows helpers via ctypes (no pywin32 needed).
Every function degrades gracefully on non-Windows so the app can be smoke-tested elsewhere."""
import os
import re
import sys
import json
import glob
import ctypes
import subprocess
import threading

IS_WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000

if IS_WIN:
    from ctypes import wintypes
    import winreg

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    kernel32.GetTickCount.restype = wintypes.DWORD


def foreground():
    """(hwnd, pid, title, classname) of the active window, or None."""
    if not IS_WIN:
        return None
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    cls = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, cls, 128)
    return hwnd, pid.value, buf.value, cls.value


def idle_seconds():
    if not IS_WIN:
        return 0.0
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    return ((kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


def is_fullscreen(hwnd):
    """True if the window covers its whole monitor (fullscreen video/game)."""
    if not IS_WIN or not hwnd:
        return False
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    mon = user32.MonitorFromWindow(hwnd, 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


def is_admin():
    if not IS_WIN:
        return False
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(script):
    """Restart this script elevated (UAC prompt). Returns True if the prompt was accepted."""
    if not IS_WIN:
        return False
    exe = pythonw()
    params = f'"{script}"'
    rc = shell32.ShellExecuteW(None, "runas", exe, params, os.path.dirname(script), 1)
    return rc > 32


def pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


# ---------- start with Windows ----------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_startup(enabled, script):
    if not IS_WIN:
        return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, "hush", 0, winreg.REG_SZ, f'"{pythonw()}" "{script}" --tray')
        else:
            try:
                winreg.DeleteValue(k, "hush")
            except FileNotFoundError:
                pass
    return True


def get_startup():
    if not IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "hush")
            return True
    except OSError:
        return False


# ---------- browser Secure DNS policy (needs admin) ----------
DOH_KEYS = [r"SOFTWARE\Policies\Google\Chrome", r"SOFTWARE\Policies\BraveSoftware\Brave",
            r"SOFTWARE\Policies\Microsoft\Edge"]


def set_doh_policy(disable):
    """Turn browser Secure DNS off so the hosts-file block works. Needs admin."""
    if not IS_WIN or not is_admin():
        return False
    for path in DOH_KEYS:
        try:
            if disable:
                with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, "DnsOverHttpsMode", 0, winreg.REG_SZ, "off")
            else:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, "DnsOverHttpsMode")
        except OSError:
            pass
    ff = r"SOFTWARE\Policies\Mozilla\Firefox\DNSOverHTTPS"
    try:
        if disable:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, ff, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "Enabled", 0, winreg.REG_DWORD, 0)
        else:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ff, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "Enabled")
    except OSError:
        pass
    return True


# ---------- hosts file ----------
HOSTS = r"C:\Windows\System32\drivers\etc\hosts"
H_START = "# >>> hush. focus block"
H_END = "# <<< hush. focus block"


def write_hosts_block(domains):
    """Replace hush.'s block in the hosts file. Empty list = remove it. Needs admin."""
    if not IS_WIN or not is_admin():
        return False
    try:
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        txt = re.sub(r"\n?" + re.escape(H_START) + r".*?" + re.escape(H_END) + r"\n?", "\n", txt, flags=re.S)
        txt = txt.rstrip("\n") + "\n"
        if domains:
            lines = [H_START]
            for d in domains:
                for pre in ("", "www.", "m."):
                    lines.append(f"0.0.0.0 {pre}{d}")
            lines.append(H_END)
            txt += "\n".join(lines) + "\n"
        with open(HOSTS, "w", encoding="utf-8") as f:
            f.write(txt)
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, creationflags=NO_WINDOW)
        return True
    except OSError:
        return False


# ---------- game detection ----------
def _steam_common_dirs():
    out = set()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            sp = os.path.normpath(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        sp = r"C:\Program Files (x86)\Steam"
    libs = {sp}
    vdf = os.path.join(sp, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, encoding="utf-8", errors="ignore") as f:
            for m in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                libs.add(os.path.normpath(m.group(1).replace("\\\\", "\\")))
    except OSError:
        pass
    for lib in libs:
        common = os.path.join(lib, "steamapps", "common")
        if os.path.isdir(common):
            out.add(common)
    return out


def detect_games():
    """List of {id, name, path, source} for installed games."""
    if not IS_WIN:
        return []
    games = {}

    def add(path, name, source):
        path = os.path.normpath(path)
        if os.path.isdir(path):
            games[path.lower()] = {"id": path.lower(), "name": name, "path": path, "source": source}

    for common in _steam_common_dirs():
        try:
            for d in os.listdir(common):
                if d.lower().startswith("steamworks") or d.lower() == "steam controller configs":
                    continue
                add(os.path.join(common, d), d, "Steam")
        except OSError:
            pass
    for item in glob.glob(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests\*.item"):
        try:
            with open(item, encoding="utf-8", errors="ignore") as f:
                j = json.load(f)
            add(j.get("InstallLocation", ""), j.get("DisplayName", "Epic game"), "Epic")
        except (OSError, ValueError):
            pass
    for root, source in ((r"C:\Riot Games", "Riot"), (r"C:\XboxGames", "Xbox")):
        if os.path.isdir(root):
            for d in os.listdir(root):
                if d.lower() in ("riot client", "gameplay", ".appxmetadata"):
                    continue
                add(os.path.join(root, d), d, source)
    return sorted(games.values(), key=lambda g: g["name"].lower())


# ---------- global hotkey ----------
def start_hotkey(callback, vk=ord("H")):
    """Ctrl+Alt+H anywhere -> callback(). Runs its own message loop thread."""
    if not IS_WIN:
        return

    def loop():
        MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, WM_HOTKEY = 0x1, 0x2, 0x4000, 0x0312
        if not user32.RegisterHotKey(None, 1, MOD_ALT | MOD_CONTROL | MOD_NOREPEAT, vk):
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                try:
                    callback()
                except Exception:
                    pass

    threading.Thread(target=loop, daemon=True, name="hotkey").start()


def round_corners(title):
    """Windows 11 native rounded corners (+ shadow) for a frameless window."""
    if not IS_WIN:
        return
    try:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            pref = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(pref), 4)
    except Exception:
        pass


def style_caption(caption="#EBE5D9", text="#1F3550", skip=("mini",)):
    """Recolour the native Windows 11 title bar to match hush. (keeps snap, resize and the normal buttons)."""
    if not IS_WIN:
        return
    def cref(h):
        h = h.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return ctypes.c_uint(r | (g << 8) | (b << 16))
    try:
        dwm = ctypes.windll.dwmapi
        for hwnd, title in own_windows():
            if any(s in title for s in skip):
                continue
            h = wintypes.HWND(hwnd)
            dark = ctypes.c_int(0)
            dwm.DwmSetWindowAttribute(h, 20, ctypes.byref(dark), 4)            # light mode caption buttons
            dwm.DwmSetWindowAttribute(h, 35, ctypes.byref(cref(caption)), 4)  # DWMWA_CAPTION_COLOR
            dwm.DwmSetWindowAttribute(h, 34, ctypes.byref(cref(caption)), 4)  # DWMWA_BORDER_COLOR
            dwm.DwmSetWindowAttribute(h, 36, ctypes.byref(cref(text)), 4)     # DWMWA_TEXT_COLOR
    except Exception:
        pass


# ---------- app identity, window icon, shortcuts ----------
def set_app_id(app_id="hush.focus.app"):
    """Gives hush. its own taskbar identity (so Windows shows our icon, not Python's)."""
    if not IS_WIN:
        return
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception:
        pass


def own_windows():
    """[(hwnd, title)] for visible-or-hidden top-level windows owned by this process."""
    if not IS_WIN:
        return []
    out, me = [], os.getpid()
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "hush." in buf.value:
                out.append((hwnd, buf.value))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


def set_window_icons(ico_path):
    """Set taskbar + title-bar icon on all hush. windows."""
    if not IS_WIN or not os.path.exists(ico_path):
        return
    try:
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        big = user32.LoadImageW(None, ico_path, 1, 32, 32, 0x10)
        small = user32.LoadImageW(None, ico_path, 1, 16, 16, 0x10)
        for hwnd, _ in own_windows():
            if big:
                user32.SendMessageW(hwnd, 0x80, 1, big)
            if small:
                user32.SendMessageW(hwnd, 0x80, 0, small)
    except Exception:
        pass


_PS_SHORTCUT = r"""
$ws = New-Object -ComObject WScript.Shell
$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($d in $dirs) {
  if (-not $d) { continue }
  $s = $ws.CreateShortcut((Join-Path $d 'hush.lnk'))
  $s.TargetPath = $env:HUSH_TARGET
  $s.Arguments = $env:HUSH_ARGS
  $s.WorkingDirectory = $env:HUSH_WD
  $s.IconLocation = "$($env:HUSH_ICO),0"
  $s.Description = 'hush. focus timer'
  $s.Save()
}
"""


def create_shortcuts(script, ico):
    """Desktop + Start-menu shortcut 'hush' with our icon. Returns True on success."""
    if not IS_WIN:
        return False
    env = dict(os.environ, HUSH_TARGET=pythonw(), HUSH_ARGS=f'"{script}"', HUSH_WD=os.path.dirname(script), HUSH_ICO=ico)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_SHORTCUT],
                           env=env, capture_output=True, creationflags=NO_WINDOW, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


_PS_ICONS = r"""
Add-Type -AssemblyName System.Drawing
$items = Get-Content -Raw -LiteralPath $env:HUSH_JOBS | ConvertFrom-Json
foreach ($i in $items) {
  try {
    $ic = [System.Drawing.Icon]::ExtractAssociatedIcon($i.exe)
    if ($ic) { $ic.ToBitmap().Save($i.out, [System.Drawing.Imaging.ImageFormat]::Png) }
  } catch {}
}
"""


def extract_icons(jobs, tmp_dir):
    """jobs: [{'exe': path, 'out': png_path}] -> writes PNGs. One PowerShell call for the whole batch."""
    if not IS_WIN or not jobs:
        return
    jf = os.path.join(tmp_dir, "icon_jobs.json")
    with open(jf, "w", encoding="utf-8") as f:
        json.dump(jobs, f)
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_ICONS],
                       env=dict(os.environ, HUSH_JOBS=jf), capture_output=True, creationflags=NO_WINDOW, timeout=60)
    except Exception:
        pass


def open_path(path):
    if IS_WIN:
        os.startfile(path)  # noqa


def reveal_file(path):
    """Open Explorer with the file selected."""
    if IS_WIN and os.path.isfile(path):
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
