"""Cloud sync through your own Cloudflare Worker (see cloud/deploy.ps1).

Uploads the laptop's daily totals and focus state; downloads the phone's daily totals so Stats can show
phone and combined screen time. Config lives outside the repo in %LOCALAPPDATA%/hush/cloud.json.
"""
import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from . import stats

log = logging.getLogger("hush.cloud")


class Cloud(threading.Thread):
    def __init__(self, db, engine, categorize, data_dir):
        super().__init__(daemon=True, name="cloud")
        self.db, self.engine, self.categorize = db, engine, categorize
        self.cfg_path = os.path.join(data_dir, "cloud.json")
        self.cfg = self._load()
        self.sent = {}            # day -> hash of last upload
        self.last_focus = None    # last focus state pushed
        self.last_focus_t = 0.0
        self.last_pull = 0.0
        self.since = (db.get("cloud_since") or 0)
        self.ok_at = 0.0
        self.error = ""
        self._wake = threading.Event()

    def _load(self):
        try:
            with open(self.cfg_path, encoding="utf-8-sig") as f:
                c = json.load(f)
            return c if c.get("url") and c.get("key") else None
        except (OSError, ValueError):
            return None

    @property
    def enabled(self):
        return self.cfg is not None

    def share_config(self):
        """For pairing the phone over the LAN link."""
        return {"url": self.cfg["url"], "key": self.cfg["key"]} if self.cfg else None

    def status(self):
        return {"enabled": self.enabled, "ok": time.time() - self.ok_at < 600 if self.ok_at else False,
                "last_ok": self.ok_at, "error": self.error,
                "url": self.cfg["url"] if self.cfg else "", "phone_days": len(self.phone_cache())}

    def phone_cache(self):
        return self.db.get("cloud_phone_days") or {}

    # ---------- http ----------
    def _req(self, method, path, body=None, timeout=15):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.cfg["url"] + path, data=data, method=method,
                                   headers={"authorization": "Bearer " + self.cfg["key"], "content-type": "application/json",
                                            "user-agent": "hush-laptop/1.3"})
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return json.loads(f.read() or b"{}")

    # ---------- sync steps ----------
    def push_days(self):
        today = date.today()
        days = stats.laptop_days(self.db, today - timedelta(days=1), today, self.categorize)
        for d in (today - timedelta(days=1), today):
            if d not in days:
                continue
            payload = stats.day_payload(days[d])
            # blocked attempts that day ride along so the phone's combined view can show them
            a, b = stats.bounds(d)
            payload["blocked"] = len(self.db.events_between(a, b, "block"))
            h = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if self.sent.get(d.isoformat()) == h:
                continue
            self._req("PUT", "/day", {"device": "laptop", "day": d.isoformat(), "data": payload})
            self.sent[d.isoformat()] = h

    def push_focus(self, force=False):
        st = self.engine.state()
        cur = (self.engine.blocking_active(), st["paused"], st["label"], st["phase"])
        now = time.time()
        # on every change, and every 2 min while focusing so the cloud's countdown stays accurate
        if not force and cur == self.last_focus and not (cur[0] and now - self.last_focus_t > 120):
            return
        self._req("PUT", "/focus", {"focus": cur[0], "paused": cur[1], "label": cur[2], "left": st["left"]})
        self.last_focus, self.last_focus_t = cur, now

    def pull(self):
        today = date.today()
        r = self._req("GET", f"/days?from={(today - timedelta(days=40)).isoformat()}&to={today.isoformat()}&since={self.since}")
        cache = self.phone_cache()
        changed = False
        for row in r.get("days", []):
            if row["device"] == "phone":
                cache[row["day"]] = row["data"]
                changed = True
            self.since = max(self.since, row.get("updated", 0))
        if changed:
            cutoff = (today - timedelta(days=60)).isoformat()
            cache = {k: v for k, v in cache.items() if k >= cutoff}
            self.db.set("cloud_phone_days", cache)
        self.db.set("cloud_since", self.since)
        self.last_pull = time.time()
        return changed

    def refresh(self):
        """Pull now (Stats screen opened). Returns True if anything new arrived."""
        if not self.enabled:
            return False
        try:
            ch = self.pull()
            self.ok_at, self.error = time.time(), ""
            return ch
        except Exception as e:  # network trouble is normal: keep the cached data
            self.error = str(e)[:120]
            return False

    def run(self):
        n = 0
        while True:
            if self.enabled:
                try:
                    self.push_focus()
                    if n % 6 == 0:            # every ~60 s
                        self.push_days()
                    if time.time() - self.last_pull > 300:
                        self.pull()
                    self.ok_at, self.error = time.time(), ""
                except (urllib.error.URLError, OSError, ValueError) as e:
                    self.error = str(e)[:120]
                except Exception:
                    log.exception("cloud sync")
            else:
                if n % 30 == 0:
                    self.cfg = self._load()   # pick up a fresh deploy without restarting
            n += 1
            self._wake.wait(10)
            self._wake.clear()

    def poke(self):
        self._wake.set()
