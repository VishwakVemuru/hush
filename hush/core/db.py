import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage(
  id INTEGER PRIMARY KEY, app TEXT, exe TEXT, site TEXT, title TEXT, start REAL, end REAL);
CREATE INDEX IF NOT EXISTS usage_start ON usage(start);
CREATE TABLE IF NOT EXISTS focus(
  id INTEGER PRIMARY KEY, label TEXT, mode TEXT, start REAL, end REAL, planned REAL,
  tracked REAL DEFAULT 0, distracted REAL DEFAULT 0, blocked INTEGER DEFAULT 0, completed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, target TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, text TEXT, done INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS categories(name TEXT PRIMARY KEY, category TEXT);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
"""


class DB:
    def __init__(self, path):
        self.c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.c.execute("PRAGMA journal_mode=WAL")
            self.c.executescript(SCHEMA)
            # v1.4: camera study check columns
            have = {r[1] for r in self.c.execute("PRAGMA table_info(focus)").fetchall()}
            for col in ("verified", "phone_s", "away_s"):
                if col not in have:
                    self.c.execute(f"ALTER TABLE focus ADD COLUMN {col} REAL DEFAULT 0")

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.c.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            cur = self.c.execute(sql, args)
            return cur.lastrowid

    # kv
    def get(self, key, default=None):
        r = self.q("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(r[0]["value"]) if r else default

    def set(self, key, value):
        self.x("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, json.dumps(value)))

    # usage
    def usage_insert(self, app, exe, site, title, start, end):
        return self.x("INSERT INTO usage(app,exe,site,title,start,end) VALUES(?,?,?,?,?,?)",
                      (app, exe, site, title, start, end))

    def usage_update(self, rid, end, title):
        self.x("UPDATE usage SET end=?, title=? WHERE id=?", (end, title, rid))

    def prune_usage(self, keep_days=30):
        """Delete screen-time records older than `keep_days` days (today counts as day 1). Returns rows removed."""
        import datetime as _dt
        cutoff = _dt.datetime.combine(_dt.date.today() - _dt.timedelta(days=keep_days - 1), _dt.time.min).timestamp()
        with self.lock:
            n = self.c.execute("DELETE FROM usage WHERE end < ?", (cutoff,)).rowcount
            self.c.execute("UPDATE usage SET start = ? WHERE start < ?", (cutoff, cutoff))  # trim a row that straddles the cutoff
        return n

    def usage_between(self, a, b):
        return self.q("SELECT * FROM usage WHERE end>? AND start<? ORDER BY start", (a, b))

    # focus
    def focus_start(self, label, mode, planned):
        return self.x("INSERT INTO focus(label,mode,start,end,planned) VALUES(?,?,?,?,?)",
                      (label, mode, time.time(), time.time(), planned))

    def focus_end(self, fid, tracked, distracted, blocked, completed, verified=0, phone_s=0, away_s=0):
        self.x("UPDATE focus SET end=?, tracked=?, distracted=?, blocked=?, completed=?, verified=?, phone_s=?, away_s=? WHERE id=?",
               (time.time(), tracked, distracted, blocked, int(completed), verified, phone_s, away_s, fid))

    def focus_between(self, a, b):
        return self.q("SELECT * FROM focus WHERE start>=? AND start<? ORDER BY start", (a, b))

    # events
    def event(self, kind, target):
        self.x("INSERT INTO events(ts,kind,target) VALUES(?,?,?)", (time.time(), kind, target))

    def events_between(self, a, b, kind=None):
        if kind:
            return self.q("SELECT * FROM events WHERE ts>=? AND ts<? AND kind=? ORDER BY ts", (a, b, kind))
        return self.q("SELECT * FROM events WHERE ts>=? AND ts<? ORDER BY ts", (a, b))

    # tasks
    def tasks(self):
        return self.q("SELECT * FROM tasks ORDER BY done, id")

    def task_add(self, text):
        return self.x("INSERT INTO tasks(text,created) VALUES(?,?)", (text, time.time()))

    def task_toggle(self, tid):
        self.x("UPDATE tasks SET done=1-done WHERE id=?", (tid,))

    def task_delete(self, tid):
        self.x("DELETE FROM tasks WHERE id=?", (tid,))

    def tasks_clear_done(self):
        self.x("DELETE FROM tasks WHERE done=1")

    # categories
    def categories(self):
        return {r["name"]: r["category"] for r in self.q("SELECT * FROM categories")}

    def set_category(self, name, cat):
        self.x("INSERT INTO categories(name,category) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET category=excluded.category",
               (name, cat))
