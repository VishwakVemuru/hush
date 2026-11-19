# PyInstaller spec for hush.exe (one-folder build). Run via packaging/build.ps1.
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
    hiddenimports=["pystray._win32", "webview.platforms.winforms", "webview.platforms.edgechromium", "clr"],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="hush",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="hush")
