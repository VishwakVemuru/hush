# PyInstaller spec for hush.app (macOS). Built on a Mac by .github/workflows/mac.yml.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [
    (os.path.join(ROOT, "ui"), "ui"),
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "extension"), "extension"),
]
apk = os.path.join(ROOT, "phone", "hush.apk")
if os.path.exists(apk):
    datas.append((apk, "phone"))

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["pystray._darwin", "webview.platforms.cocoa", "AppKit", "Quartz", "core.mac"],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PyQt5", "PySide6"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="hush", console=False,
          icon=os.path.join(ROOT, "assets", "icon-512.png"))
coll = COLLECT(exe, a.binaries, a.datas, name="hush")
app = BUNDLE(
    coll,
    name="hush.app",
    icon=os.path.join(ROOT, "assets", "icon-512.png"),
    bundle_identifier="app.hush.focus",
    info_plist={
        "CFBundleName": "hush.",
        "CFBundleDisplayName": "hush.",
        "CFBundleShortVersionString": os.environ.get("HUSH_VERSION", "1.4.0"),
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "NSCameraUsageDescription": "hush. uses the camera during focus sessions to check you're at your desk and not on your phone. Nothing is recorded or sent anywhere.",
        "NSAppleEventsUsageDescription": "hush. checks which app is in front to track screen time.",
    },
)
