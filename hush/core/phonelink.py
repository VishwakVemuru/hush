"""Phone link: lets the hush. Android app on the same Wi-Fi mirror laptop focus sessions.

Runs on its own port, separate from the extension bridge (which stays bound to 127.0.0.1).
Everything except /ping and the APK download needs the pairing code, and the only thing a
paired phone can change is the blocked-attempt counter.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 47322
log = logging.getLogger("hush.phone")


def lan_ip():
    """Best guess at this laptop's Wi-Fi/LAN address (no packets are actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class PhoneLink:
    MAX_FAILS = 8          # wrong codes allowed per address ...
    LOCK_SECS = 15 * 60    # ... before it's locked out for this long

    def __init__(self, db, engine, hub, apk_path, cloud=None):
        self.db, self.engine, self.hub, self.apk_path, self.cloud = db, engine, hub, apk_path, cloud
        self.seen = 0.0
        self.seen_name = ""
        self.server = None
        self.code = db.get("phone_code") or self._new_code()
        self.fails = {}        # ip -> [count, first_fail_time, locked_until]
        self.flock = threading.Lock()

    def check_code(self, ip, given):
        """Constant-time code check with a per-address lockout, so the 8 digits can't be brute-forced."""
        now = time.time()
        with self.flock:
            f = self.fails.get(ip)
            if f and f[2] > now:
                return None  # locked out
            if hmac.compare_digest(str(given), self.code):
                self.fails.pop(ip, None)
                return True
            if not f or now - f[1] > self.LOCK_SECS:
                f = [0, now, 0.0]
            f[0] += 1
            if f[0] >= self.MAX_FAILS:
                f[2] = now + self.LOCK_SECS
                log.warning("phone link: %s locked out after %d wrong codes", ip, f[0])
            self.fails[ip] = f
            return False

    def _new_code(self):
        code = f"{secrets.randbelow(10 ** 8):08d}"
        self.db.set("phone_code", code)
        return code

    def regenerate(self):
        self.code = self._new_code()
        self.seen = 0.0
        with self.flock:
            self.fails.clear()
        return self.info()

    def laptop_id(self):
        # lets the phone recognise *this* laptop when its IP changes, without revealing the code
        return hashlib.sha256(("hush-phone:" + self.code).encode()).hexdigest()[:12]

    def connected(self):
        return time.time() - self.seen < 30

    def info(self):
        ip = lan_ip()
        return {"ip": ip, "port": PORT, "code": self.code, "connected": self.connected(),
                "phone": self.seen_name, "running": self.server is not None,
                "apk": os.path.isfile(self.apk_path), "apk_url": f"http://{ip}:{PORT}/hush.apk"}

    def start(self):
        link = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj=None):
                body = json.dumps(obj or {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _authed(self):
                """True if the code is right; otherwise sends 403 (wrong) or 429 (locked out) and returns False."""
                qs = parse_qs(urlparse(self.path).query)
                given = self.headers.get("X-Hush-Code") or (qs.get("code") or [""])[0]
                ok = link.check_code(self.client_address[0], given)
                if ok:
                    return True
                if ok is None:
                    self._send(429, {"error": "too many wrong codes, try again later"})
                else:
                    self._send(403, {"error": "wrong code"})
                return False

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/ping":
                    return self._send(200, {"app": "hush", "v": 1, "id": link.laptop_id()})
                if path == "/hush.apk":
                    return self._apk()
                if path == "/":
                    return self._page()
                if path == "/cloud":
                    # hands the paired phone the sync address + key, so it can sync away from home Wi-Fi
                    if not self._authed():
                        return
                    cfg = link.cloud.share_config() if link.cloud else None
                    return self._send(200, cfg or {"url": "", "key": ""})
                if path == "/state":
                    if not self._authed():
                        return
                    link.seen = time.time()
                    link.seen_name = str(self.headers.get("X-Hush-Device") or "")[:60]
                    st = link.engine.state()
                    return self._send(200, {"focus": link.engine.blocking_active(), "left": st["left"],
                                            "paused": st["paused"], "phase": st["phase"], "label": st["label"],
                                            "mode": st["mode"], "id": link.laptop_id(),
                                            "cloud": bool(link.cloud and link.cloud.enabled)})
                self._send(404)

            def do_POST(self):
                path = urlparse(self.path).path
                if path != "/blocked":
                    return self._send(404)
                if not self._authed():
                    return
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    data = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
                except ValueError:
                    data = {}
                app = str(data.get("app") or "an app")[:60]
                if link.engine.blocking_active():
                    link.engine.add_block(f"{app} (phone)")
                    link.hub.notify(f"hush. {app} on your phone can wait · {link.engine.minutes_left()} min left", "block")
                self._send(200)

            def _apk(self):
                if not os.path.isfile(link.apk_path):
                    return self._send(404, {"error": "phone app not built yet"})
                size = os.path.getsize(link.apk_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header("Content-Disposition", 'attachment; filename="hush.apk"')
                self.send_header("Content-Length", str(size))
                self.end_headers()
                with open(link.apk_path, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)

            def _page(self):
                # tiny landing page: opening http://<laptop>:47322 on the phone proves the firewall lets it through
                body = ("<!doctype html><meta name=viewport content='width=device-width'>"
                        "<body style='font-family:sans-serif;padding:24px;background:#F3EFE7;color:#1d2a3a'>"
                        "<h1 style='font-style:italic;font-family:serif'>hush.</h1>"
                        "<p>Your phone can reach your laptop.</p>"
                        "<p><a href='/hush.apk' style='font-size:20px'>Download the hush. phone app</a></p>").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            self.server = ThreadingHTTPServer(("0.0.0.0", PORT), H)
        except OSError:
            log.warning("phone link port %s busy", PORT)
            self.server = None
            return False
        threading.Thread(target=self.server.serve_forever, daemon=True, name="phonelink").start()
        return True
