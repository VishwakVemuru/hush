"""Focus / break state machine. Lives in the backend so hard mode survives UI tricks and restarts."""
import re
import secrets
import threading
import time

PHRASE = "i am choosing to stop focusing right now"
GRACE = 10  # seconds to save your game before blocked apps close


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
        self.s = self._blank()
        self._restore()

    def _blank(self):
        return {"phase": "idle", "label": "", "mode": "soft", "focus_min": 50, "break_min": 10,
                "sessions": 4, "index": 1, "ends_at": 0.0, "paused": False, "remaining": 0.0,
                "phase_total": 0.0, "focus_id": None, "grace_until": 0.0,
                "cur": {"tracked": 0, "distracted": 0, "blocked": 0},
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
            self.s = base
            if self.s["phase"] == "focus":
                self.s["grace_until"] = now + GRACE
        else:
            if st.get("focus_id"):
                c = st.get("cur", {})
                self.db.focus_end(st["focus_id"], c.get("tracked", 0), c.get("distracted", 0), c.get("blocked", 0), True)
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
        s.update(phase="focus", paused=False, ends_at=time.time() + secs, phase_total=secs,
                 grace_until=time.time() + GRACE, cur={"tracked": 0, "distracted": 0, "blocked": 0})
        s["focus_id"] = self.db.focus_start(s["label"], s["mode"], secs)

    def _close_focus(self, completed):
        s = self.s
        if s["focus_id"]:
            c = s["cur"]
            self.db.focus_end(s["focus_id"], c["tracked"], c["distracted"], c["blocked"], completed)
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
                    "grace": max(0, s["grace_until"] - time.time()) if s["phase"] == "focus" else 0,
                    "summary": self.summary, "now": time.time()}
