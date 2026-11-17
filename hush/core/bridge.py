"""Tiny localhost API for the hush. browser extension (and single-instance handoff)."""
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 47321


class Bridge:
    def __init__(self, engine, blocker, hub, on_show):
        self.engine, self.blocker, self.hub, self.on_show = engine, blocker, hub, on_show
        self._activity = None
        self.ext_seen = 0.0
        self.server = None

    def activity(self):
        return self._activity

    def extension_connected(self):
        return time.time() - self.ext_seen < 90

    @staticmethod
    def ping_existing():
        """If hush. is already running, ask it to show its window. True if it answered."""
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/show", data=b"{}", method="POST",
                                         headers={"X-Hush": "1", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1.5)
            return True
        except Exception:
            return False

    def start(self):
        bridge = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _allowed(self):
                # Custom header forces a CORS preflight, which we refuse, so random websites can't call us.
                origin = self.headers.get("Origin", "")
                return self.headers.get("X-Hush") == "1" and (not origin or origin.startswith(("chrome-extension://", "moz-extension://")))

            def _send(self, code, obj=None):
                body = json.dumps(obj or {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    return json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                except ValueError:
                    return {}

            def do_OPTIONS(self):
                self._send(403)

            def do_GET(self):
                if not self._allowed():
                    return self._send(403)
                if self.path.startswith("/state"):
                    bridge.ext_seen = time.time()
                    st = bridge.engine.state()
                    return self._send(200, {"focus": bridge.engine.blocking_active(), "sites": bridge.blocker.enabled_sites(),
                                            "shorts": bridge.blocker.shorts(), "endsAt": st["ends_at"], "left": st["left"],
                                            "label": st["label"], "phase": st["phase"], "paused": st["paused"]})
                self._send(404)

            def do_POST(self):
                if not self._allowed():
                    return self._send(403)
                data = self._json()
                if self.path.startswith("/activity"):
                    bridge.ext_seen = time.time()
                    d = str(data.get("domain") or "")[:120]
                    bridge._activity = {"domain": d, "ts": time.time()} if d else None
                    return self._send(200)
                if self.path.startswith("/blocked"):
                    site = str(data.get("site") or "a site")[:120]
                    if bridge.engine.blocking_active():
                        bridge.engine.add_block(site)
                        bridge.hub.notify(f"hush. {site} can wait · {bridge.engine.minutes_left()} min left", "block")
                    return self._send(200)
                if self.path.startswith("/show"):
                    threading.Thread(target=bridge.on_show, daemon=True).start()
                    return self._send(200)
                self._send(404)

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", PORT), H)
        except OSError:
            return False
        threading.Thread(target=self.server.serve_forever, daemon=True, name="bridge").start()
        return True
