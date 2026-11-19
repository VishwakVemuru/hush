"""hush. cloud: your account, friends and leaderboard, plus screen-time sync (Cloudflare Worker, see cloud/).

Signed in, everything goes through your account's session token. Before signing in, the older single-user
setup (a sync key in cloud.json, from cloud/deploy.ps1) still works for screen-time sync; the first sign-in on
that laptop moves the old data into the account.
"""
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from . import stats

log = logging.getLogger("hush.cloud")

# The shared hush. service. Anyone can sign up; every request after that needs your own session token.
DEFAULT_URL = "https://hush-sync.draw-track-racer.workers.dev"
UA = "hush-laptop/1.4"


class CloudError(Exception):
    def __init__(self, msg, status=0):
        super().__init__(msg)
        self.status = status


class Cloud(threading.Thread):
    def __init__(self, db, engine, categorize, data_dir):
        super().__init__(daemon=True, name="cloud")
        self.db, self.engine, self.categorize = db, engine, categorize
        self.cfg_path = os.path.join(data_dir, "cloud.json")
        self.legacy = self._load_legacy()
        self.sent = {}            # day -> hash of last upload
        self.last_focus = None
        self.last_focus_t = 0.0
        self.last_pull = 0.0
        self.since = db.get("cloud_since") or 0
        self.ok_at = 0.0
        self.error = ""
        self._wake = threading.Event()
        self.lb_cache = {}

    # ---------- config ----------
    def _load_legacy(self):
        try:
            with open(self.cfg_path, encoding="utf-8-sig") as f:
                c = json.load(f)
            return c if c.get("url") and c.get("key") else None
        except (OSError, ValueError):
            return None

    @property
    def account(self):
        return self.db.get("account") or None

    @property
    def url(self):
        a = self.account
        return (a and a.get("url")) or (self.legacy and self.legacy["url"]) or DEFAULT_URL

    @property
    def token(self):
        a = self.account
        return (a and a.get("token")) or (self.legacy and self.legacy["key"]) or ""

    @property
    def enabled(self):
        return bool(self.token)

    @property
    def signed_in(self):
        return bool(self.account and self.account.get("token"))

    def share_config(self):
        """Handed to the paired phone over the LAN link so it syncs as the same account."""
        return {"url": self.url, "key": self.token} if self.enabled else None

    def status(self):
        a = self.account or {}
        return {"enabled": self.enabled, "signed_in": self.signed_in, "username": a.get("username", ""),
                "display": a.get("display", ""), "ok": time.time() - self.ok_at < 600 if self.ok_at else False,
                "last_ok": self.ok_at, "error": self.error, "url": self.url, "phone_days": len(self.phone_cache())}

    def phone_cache(self):
        return self.db.get("cloud_phone_days") or {}

    def device_id(self):
        d = self.db.get("device_id")
        if not d:
            d = secrets.token_hex(6)
            self.db.set("device_id", d)
        return d

    # ---------- http ----------
    def _req(self, method, path, body=None, timeout=15, token=None, auth=True):
        data = json.dumps(body).encode() if body is not None else None
        h = {"content-type": "application/json", "user-agent": UA}
        tok = token if token is not None else self.token
        if auth and tok:
            h["authorization"] = "Bearer " + tok
        r = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as f:
                return json.loads(f.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read() or b"{}").get("error") or f"error {e.code}"
            except ValueError:
                msg = f"error {e.code}"
            if e.code == 401 and self.signed_in and path not in ("/auth/login", "/auth/signup"):
                # token was revoked (password changed elsewhere, or signed out): forget it
                self.db.set("account", {**self.account, "token": ""})
            raise CloudError(msg, e.code)
        except (urllib.error.URLError, OSError) as e:
            raise CloudError("Can't reach the hush. server. Check your internet.") from e

    # ---------- account ----------
    def _signed_in(self, r):
        self.db.set("account", {"url": self.url, "token": r["token"], "username": r["user"]["username"],
                                "display": r["user"]["display"]})
        # first sign-in on the laptop that ran the old single-user sync: bring that data along
        if self.legacy:
            try:
                self._req("POST", "/auth/claim-legacy", {"key": self.legacy["key"]})
                log.info("moved legacy sync data into the account")
            except CloudError as e:
                log.info("legacy claim skipped: %s", e)
        self.since = 0
        self.db.set("cloud_since", 0)
        self.sent.clear()
        self.last_focus = None
        self.poke()
        return self.status()

    def signup(self, username, password, display=""):
        r = self._req("POST", "/auth/signup", {"username": username, "password": password, "display": display,
                                               "device": "laptop"}, auth=False)
        return self._signed_in(r)

    def login(self, username, password):
        r = self._req("POST", "/auth/login", {"username": username, "password": password, "device": "laptop"}, auth=False)
        return self._signed_in(r)

    def logout(self):
        if self.signed_in:
            try:
                self._req("POST", "/auth/logout", {})
            except CloudError:
                pass
        self.db.set("account", None)
        self.lb_cache = {}
        return self.status()

    # ---------- friends & leaderboard ----------
    def friends(self):
        return self._req("GET", "/friends")

    def add_friend(self, username):
        return self._req("POST", "/friends/request", {"username": username})

    def accept_friend(self, username):
        return self._req("POST", "/friends/accept", {"username": username})

    def remove_friend(self, username):
        return self._req("DELETE", "/friends/" + urllib.request.quote(username))

    def leaderboard(self, rng="week"):
        today = datetime.combine(date.today(), datetime.min.time())
        start = today - timedelta(days={"day": 0, "week": 6, "month": 29}.get(rng, 6))
        tz = round((datetime.now() - datetime.utcnow()).total_seconds() / 60)
        r = self._req("GET", f"/leaderboard?from={int(start.timestamp() * 1000)}&tz={tz}")
        self.lb_cache[rng] = r
        return r

    # ---------- focus log ----------
    def queue_focus_log(self, rec):
        """Called when a focus session ends. Uploaded by the sync loop (kept if offline)."""
        q = self.db.get("focus_log_queue") or []
        q.append(rec)
        self.db.set("focus_log_queue", q[-200:])
        self.poke()

    def flush_focus_log(self):
        if not self.signed_in:
            return
        q = self.db.get("focus_log_queue") or []
        keep = []
        for rec in q:
            try:
                self._req("POST", "/focus-log", rec)
            except CloudError as e:
                if e.status in (0, 401, 429, 500, 502, 503):
                    keep.append(rec)   # try again later
                else:
                    log.info("focus log rejected (%s): %s", e.status, e)
        self.db.set("focus_log_queue", keep)

    # ---------- screen-time sync ----------
    def push_days(self):
        today = date.today()
        days = stats.laptop_days(self.db, today - timedelta(days=1), today, self.categorize)
        for d in (today - timedelta(days=1), today):
            if d not in days:
                continue
            payload = stats.day_payload(days[d])
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
            self.db.set("cloud_phone_days", {k: v for k, v in cache.items() if k >= cutoff})
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
        except Exception as e:
            self.error = str(e)[:120]
            return False

    def run(self):
        n = 0
        while True:
            if self.enabled:
                try:
                    self.push_focus()
                    if n % 6 == 0:
                        self.push_days()
                        self.flush_focus_log()
                    if time.time() - self.last_pull > 300:
                        self.pull()
                    self.ok_at, self.error = time.time(), ""
                except CloudError as e:
                    self.error = str(e)[:120]
                except Exception:
                    log.exception("cloud sync")
            elif n % 30 == 0:
                self.legacy = self._load_legacy()
            n += 1
            self._wake.wait(10)
            self._wake.clear()

    def poke(self):
        self._wake.set()
