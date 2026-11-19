"""Focus / break state machine. Lives in the backend so hard mode survives UI tricks and restarts."""
import re
import secrets
import threading
import time

PHRASE = "i am choosing to stop focusing right now"
GRACE = 10  # seconds to save your game before blocked apps close
PRESENCE_FRESH = 5  # a camera reading counts for this many seconds
# per-session counters: tracked/distracted come from the app tracker, the rest tick every second of focus
CUR0 = {"tracked": 0, "distracted": 0, "blocked": 0, "elapsed": 0, "verified": 0, "phone": 0, "away": 0, "camera": 0}


def _norm(s):
    return re.sub(r"[^a-z ]", "", (s or "").lower()).strip()


class FocusEngine:
    def __init__(self, db, hub):
        self.db, self.hub = db, hub
        self.lock = threading.RLock()
        self.listeners = []
        self.tokens = {}
        self.summary = None
        self._last_save = 0
        self.presence = ("", 0.0)   # (present|away|phone, time) from the camera check
        self.s = self._blank()
        self._restore()

    def _blank(self):
        return {"phase": "idle", "label": "", "mode": "soft", "focus_min": 50, "break_min": 10,
                "sessions": 4, "index": 1, "ends_at": 0.0, "paused": False, "remaining": 0.0,
                "phase_total": 0.0, "focus_id": None, "grace_until": 0.0, "started_at": 0.0,
                "cur": dict(CUR0),
                "cycle": {"tracked": 0, "distracted": 0, "blocked": 0, "done": 0, "started": 0}}

    # ---------- persistence ----------
    def _save(self):
        self.db.set("focus_state", self.s)
        self._last_save = time.time()

    def _restore(self):
        st = self.db.get("focus_state")
        if not st or st.get("phase", "idle") == "idle":
            return
        now = time.time()
        if st.get("paused") or st.get("ends_at", 0) > now:
            base = self._blank()
            base.update(st)
            base["cur"] = {**CUR0, **(st.get("cur") or {})}
            self.s = base
            if self.s["phase"] == "focus":
                self.s["grace_until"] = now + GRACE
        else:
            if st.get("focus_id"):
                c = {**CUR0, **(st.get("cur") or {})}
                self.db.focus_end(st["focus_id"], c["tracked"], c["distracted"], c["blocked"], True,
                                  c["verified"], c["phone"], c["away"])
                self._log_session(st, c, True, end=st.get("ends_at") or now)
            self.db.set("focus_state", self._blank())

    def _emit(self, what):
        for fn in self.listeners:
            try:
                fn(what)
            except Exception:
                pass

    # ---------- helpers ----------
    def _left(self):
        s = self.s
        if s["phase"] == "idle":
            return 0.0
        return max(0.0, s["remaining"] if s["paused"] else s["ends_at"] - time.time())

    def _begin_focus(self):
        s = self.s
        secs = s["focus_min"] * 60
        s.update(phase="focus", paused=False, ends_at=time.time() + secs, phase_total=secs, started_at=time.time(),
                 grace_until=time.time() + GRACE, cur=dict(CUR0))
        s["focus_id"] = self.db.focus_start(s["label"], s["mode"], secs)

    def _close_focus(self, completed):
        s = self.s
        if s["focus_id"]:
            c = s["cur"]
            self.db.focus_end(s["focus_id"], c["tracked"], c["distracted"], c["blocked"], completed,
                              c["verified"], c["phone"], c["away"])
            self._log_session(s, c, completed)
            for k in ("tracked", "distracted", "blocked"):
                s["cycle"][k] += c[k]
            if completed:
                s["cycle"]["done"] += 1
        s["focus_id"] = None

    def _finish(self, early=False):
        s = self.s
        cy = s["cycle"]
        t = cy["tracked"]
        self.summary = {"id": secrets.token_hex(4), "label": s["label"], "early": early,
                        "focused": max(0, t - cy["distracted"]), "score": round(100 * (1 - cy["distracted"] / t)) if t else None,
                        "blocked": cy["blocked"], "done": cy["done"], "sessions": s["sessions"]}
        keep = {k: s[k] for k in ("label", "mode", "focus_min", "break_min", "sessions")}
        self.s = self._blank()
        self.s.update(keep)
        self._save()
        self.hub.notify("Ended early. Every minute still counts." if early else
                        f"Session complete · {self.summary['focused'] // 60} min focused", "success", system=True)
        self._emit("idle")

    # ---------- public ----------
    def start(self, label="", focus_min=50, break_min=10, sessions=4, mode="soft"):
        with self.lock:
            if self.s["phase"] != "idle":
                return {"ok": False, "error": "Already running"}
            s = self.s
            s.update(label=(label or "").strip()[:80], focus_min=max(1, min(240, int(focus_min))),
                     break_min=max(1, min(60, int(break_min))), sessions=max(1, min(12, int(sessions))),
                     mode="hard" if mode == "hard" else "soft", index=1)
            s["cycle"] = {"tracked": 0, "distracted": 0, "blocked": 0, "done": 0, "started": time.time()}
            self.summary = None
            self._begin_focus()
            self._save()
        self._emit("focus")
        return {"ok": True}

    def pause(self):
        with self.lock:
            s = self.s
            if s["phase"] == "idle" or s["paused"]:
                return {"ok": False}
            if s["mode"] == "hard" and s["phase"] == "focus":
                return {"ok": False, "error": "Hard mode: no pausing"}
            s["remaining"] = self._left()
            s["paused"] = True
            self._save()
        self._emit("pause")
        return {"ok": True}

    def resume(self):
        with self.lock:
            s = self.s
            if not s["paused"]:
                return {"ok": False}
            s["ends_at"] = time.time() + s["remaining"]
            s["paused"] = False
            self._save()
        self._emit("resume")
        return {"ok": True}

    def skip(self):
        with self.lock:
            s = self.s
            if s["phase"] == "idle":
                return {"ok": False}
            if s["phase"] == "focus" and s["mode"] == "hard":
                return {"ok": False, "error": "Hard mode: can't skip focus"}
            self._advance(skipped=True)
        return {"ok": True}

    def request_stop(self):
        t = secrets.token_hex(8)
        self.tokens[t] = time.time()
        return t

    def stop(self, proof=None):
        with self.lock:
            s = self.s
            if s["phase"] == "idle":
                return {"ok": True}
            if s["mode"] == "hard":
                return {"ok": False, "error": "Hard mode is locked until the cycle ends"}
            if s["phase"] == "focus":
                proof = proof or {}
                ok = False
                if proof.get("type") == "phrase" and _norm(proof.get("text")) == PHRASE:
                    ok = True
                if proof.get("type") == "wait":
                    t0 = self.tokens.get(proof.get("token"))
                    ok = t0 is not None and time.time() - t0 >= 59
                if not ok:
                    return {"ok": False, "error": "Unlock not complete"}
                self._close_focus(False)
            self._finish(early=True)
        return {"ok": True}

    def _advance(self, skipped=False):
        s = self.s
        if s["phase"] == "focus":
            self._close_focus(not skipped)
            if s["index"] >= s["sessions"]:
                self._finish()
                return
            secs = s["break_min"] * 60
            s.update(phase="break", paused=False, ends_at=time.time() + secs, phase_total=secs)
            self._save()
            self.hub.notify(f"Break · {s['break_min']} min. Step away from the screen.", "break", system=True)
            self._emit("break")
        elif s["phase"] == "break":
            s["index"] += 1
            self._begin_focus()
            self._save()
            self.hub.notify(f"Back to focus · session {s['index']} of {s['sessions']}", "info", system=True)
            self._emit("focus")

    def tick(self):
        with self.lock:
            s = self.s
            if s["phase"] == "idle" or s["paused"]:
                return
            if time.time() >= s["ends_at"]:
                self._advance()
            elif time.time() - self._last_save > 20:
                self._save()

    def on_second(self, distracting):
        with self.lock:
            s = self.s
            if s["phase"] == "focus" and not s["paused"]:
                s["cur"]["tracked"] += 1
                if distracting:
                    s["cur"]["distracted"] += 1

    def set_presence(self, state):
        """Latest camera reading: 'present', 'away' or 'phone'."""
        if state in ("present", "away", "phone"):
            self.presence = (state, time.time())

    def tick_second(self):
        """Called once a second whether or not you're touching the keyboard (reading a book counts)."""
        with self.lock:
            s = self.s
            if s["phase"] != "focus" or s["paused"]:
                return
            c = s["cur"]
            c["elapsed"] += 1
            state, ts = self.presence
            if state and time.time() - ts <= PRESENCE_FRESH:
                c["camera"] = 1
                if state == "present":
                    c["verified"] += 1
                elif state == "phone":
                    c["phone"] += 1
                else:
                    c["away"] += 1

    def _log_session(self, s, c, completed, end=None):
        """Queue a finished focus session for the friends leaderboard (uploaded by the cloud sync)."""
        try:
            dev = self.db.get("device_id")
            if not dev:
                dev = secrets.token_hex(6)
                self.db.set("device_id", dev)
            end = end or time.time()
            start = s.get("started_at") or (end - c["elapsed"])
            wall = max(1, end - start)
            focus_s = min(c["elapsed"], int(wall))
            if focus_s < 60:
                return  # under a minute isn't worth a leaderboard row
            rec = {"client_id": f"{dev}-{s['focus_id']}", "start": int(start * 1000), "end": int(end * 1000),
                   "planned_s": int(s.get("phase_total") or 0), "focus_s": focus_s,
                   "verified_s": min(c["verified"], focus_s), "phone_s": c["phone"], "away_s": c["away"],
                   "camera": bool(c["camera"]), "completed": bool(completed)}
            q = self.db.get("focus_log_queue") or []
            q.append(rec)
            self.db.set("focus_log_queue", q[-200:])
        except Exception:
            pass

    def add_block(self, target):
        with self.lock:
            if self.s["phase"] == "focus":
                self.s["cur"]["blocked"] += 1
        self.db.event("block", target)

    def blocking_active(self):
        return self.s["phase"] == "focus"

    def in_grace(self):
        return time.time() < self.s["grace_until"]

    def minutes_left(self):
        return max(1, round(self._left() / 60))

    def state(self):
        with self.lock:
            s = self.s
            c = s["cur"]
            return {"phase": s["phase"], "label": s["label"], "mode": s["mode"], "paused": s["paused"],
                    "left": self._left(), "ends_at": s["ends_at"], "total": s["phase_total"], "index": s["index"],
                    "sessions": s["sessions"], "focus_min": s["focus_min"], "break_min": s["break_min"],
                    "blocked": c["blocked"], "tracked": c["tracked"], "distracted": c["distracted"],
                    "verified": c.get("verified", 0), "elapsed": c.get("elapsed", 0),
                    "presence": self.presence[0] if time.time() - self.presence[1] <= PRESENCE_FRESH else "",
                    "grace": max(0, s["grace_until"] - time.time()) if s["phase"] == "focus" else 0,
                    "summary": self.summary, "now": time.time()}
