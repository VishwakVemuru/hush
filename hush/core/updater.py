"""In-app updates from GitHub Releases.

- Installed Windows app (hush.exe): downloads the new hush-setup.exe, checks its SHA-256 against the
  .sha256 file published with the release, then runs it silently. The installer replaces the app in place
  and reopens hush; settings and data are untouched.
- Running from source or on a Mac: tells you a new version exists and opens the download page.
Never updates during a focus session.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request

from .version import VERSION

log = logging.getLogger("hush.updater")
REPO = "VishwakVemuru/hush"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
UA = f"hush-updater/{VERSION}"
FROZEN = getattr(sys, "frozen", False)


def _vt(v):
    """'v1.4.10' -> (1, 4, 10) for comparing."""
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


def _get(url, timeout=20):
    r = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(r, timeout=timeout)


class Updater:
    def __init__(self, engine, hub, quit_app):
        self.engine, self.hub, self.quit_app = engine, hub, quit_app
        self.latest = None
        self.state = "idle"   # idle | checking | downloading | installing | error
        self.progress = 0.0
        self.error = ""

    @property
    def can_install(self):
        return FROZEN and sys.platform == "win32"

    def check(self):
        """Look up the latest release. Returns a dict the UI can show."""
        self.state, self.error = "checking", ""
        try:
            with _get(API) as f:
                rel = json.loads(f.read())
            assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
            tag = rel.get("tag_name", "")
            self.latest = {"version": tag.lstrip("v"), "tag": tag, "notes": (rel.get("body") or "")[:1500],
                           "page": rel.get("html_url", f"https://github.com/{REPO}/releases/latest"),
                           "exe": assets.get("hush-setup.exe"), "sha": assets.get("hush-setup.exe.sha256")}
            self.state = "idle"
        except Exception as e:
            self.state, self.error = "error", "Couldn't check for updates (no internet?)"
            log.info("update check failed: %s", e)
            return self.status()
        return self.status()

    def status(self):
        lt = self.latest or {}
        newer = bool(lt) and _vt(lt.get("version")) > _vt(VERSION)
        return {"current": VERSION, "latest": lt.get("version"), "newer": newer, "notes": lt.get("notes", ""),
                "page": lt.get("page"), "can_install": self.can_install and bool(lt.get("exe")) and bool(lt.get("sha")),
                "state": self.state, "progress": round(self.progress, 2), "error": self.error}

    def install(self):
        """Download, verify and run the new installer (installed Windows app only). Runs in the background."""
        st = self.status()
        if not st["newer"]:
            return {"ok": False, "error": "You're already on the latest version"}
        if not st["can_install"]:
            return {"ok": False, "error": "Download the new version from the website", "page": st["page"]}
        if self.engine.state()["phase"] == "focus":
            return {"ok": False, "error": "Finish your focus session first. hush won't update mid-session."}
        if self.state in ("downloading", "installing"):
            return {"ok": True}
        threading.Thread(target=self._install, daemon=True, name="updater").start()
        return {"ok": True}

    def _install(self):
        lt = self.latest
        try:
            self.state, self.progress, self.error = "downloading", 0.0, ""
            with _get(lt["sha"]) as f:
                want = f.read().decode("utf-8", "ignore").split()[0].strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", want):
                raise ValueError("bad checksum file")
            folder = os.path.join(tempfile.gettempdir(), "hush-update")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"hush-setup-{lt['version']}.exe")
            h = hashlib.sha256()
            with _get(lt["exe"], timeout=60) as f, open(path, "wb") as out:
                total = int(f.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = f.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if total:
                        self.progress = done / total
            if h.hexdigest() != want:
                os.remove(path)
                raise ValueError("the download didn't match its checksum")
            if self.engine.state()["phase"] == "focus":
                raise ValueError("a focus session started; update again when it's over")
            self.state = "installing"
            # the installer closes hush, replaces the files and starts the new version
            subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                             creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP
            log.info("installing update %s", lt["version"])
            self.hub.notify(f"Updating to hush. {lt['version']}…", "info")
            threading.Timer(1.5, lambda: self.quit_app(force=True)).start()
        except Exception as e:
            self.state, self.error = "error", f"Update failed: {e}"
            log.warning("update failed: %s", e)
