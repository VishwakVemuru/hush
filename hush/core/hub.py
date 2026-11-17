"""Shared notification queue: UI toasts + tray/system notifications."""
import threading
import time


class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = []
        self.seq = 0
        self.tray = None
        self.ui_visible = True
        self.on_notify = None

    def notify(self, text, kind="info", system=None, title="hush."):
        with self.lock:
            self.seq += 1
            self.events.append({"id": self.seq, "text": text, "kind": kind, "ts": time.time()})
            self.events = self.events[-60:]
        if self.on_notify:
            try:
                self.on_notify(kind)
            except Exception:
                pass
        show_system = system if system is not None else not self.ui_visible
        if show_system and self.tray is not None:
            try:
                self.tray.notify(text, title)
            except Exception:
                pass

    def since(self, last_id):
        with self.lock:
            return [e for e in self.events if e["id"] > last_id]

    def last_id(self):
        with self.lock:
            return self.seq
