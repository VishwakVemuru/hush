"""Real app icons (extracted from each .exe) for Stats and the Blocklist."""
import base64
import hashlib
import os
import threading

import psutil

from . import win


class IconCache:
    def __init__(self, db, data_dir):
        self.db = db
        self.dir = os.path.join(data_dir, "icons")
        os.makedirs(self.dir, exist_ok=True)
        self.cache = {}
        self.lock = threading.Lock()
        self._busy = False
        self._tried = set()

    def _png(self, exe):
        return os.path.join(self.dir, hashlib.md5(exe.lower().encode()).hexdigest()[:16] + ".png")

    def _known_exes(self):
        """name -> exe path, from usage history and running processes."""
        m = {}
        for r in self.db.q("SELECT app, exe FROM usage WHERE exe IS NOT NULL AND exe != '' GROUP BY app"):
            m[r["app"]] = r["exe"]
            m[os.path.basename(r["exe"]).lower()] = r["exe"]
        for p in psutil.process_iter(["name", "exe"]):
            try:
                if p.info["exe"]:
                    m.setdefault(p.info["name"].lower(), p.info["exe"])
            except (psutil.Error, OSError):
                pass
        return m

    def get(self, names):
        """names (app display names or exe basenames) -> {name: data-url}. Missing ones are fetched in the background."""
        out, todo = {}, []
        known = None
        for n in names:
            if n in self.cache:
                if self.cache[n]:
                    out[n] = self.cache[n]
                continue
            if known is None:
                known = self._known_exes()
            exe = known.get(n) or known.get(str(n).lower())
            if not exe:
                continue
            png = self._png(exe)
            if os.path.exists(png):
                with open(png, "rb") as f:
                    url = "data:image/png;base64," + base64.b64encode(f.read()).decode()
                self.cache[n] = url
                out[n] = url
            elif exe not in self._tried:
                todo.append({"exe": exe, "out": png})
                self._tried.add(exe)
        if todo and not self._busy:
            self._busy = True

            def run():
                try:
                    win.extract_icons(todo, self.dir)
                finally:
                    self._busy = False
            threading.Thread(target=run, daemon=True).start()
        return out
