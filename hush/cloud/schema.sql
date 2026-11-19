-- hush. sync + friends. Safe to run repeatedly (every statement is IF NOT EXISTS).

-- legacy single-user tables (v1.3). Rows here are moved into an account by /auth/claim-legacy.
CREATE TABLE IF NOT EXISTS days (
  device  TEXT NOT NULL,
  day     TEXT NOT NULL,
  data    TEXT NOT NULL,
  updated INTEGER NOT NULL,
  PRIMARY KEY (device, day)
);
CREATE TABLE IF NOT EXISTS focus (
  id      INTEGER PRIMARY KEY,
  focus   INTEGER NOT NULL,
  paused  INTEGER NOT NULL,
  left_s  REAL NOT NULL,
  until   INTEGER NOT NULL,
  label   TEXT,
  updated INTEGER NOT NULL
);

-- accounts
CREATE TABLE IF NOT EXISTS users (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  username  TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display   TEXT NOT NULL,
  pass_hash TEXT NOT NULL,
  salt      TEXT NOT NULL,
  iters     INTEGER NOT NULL,
  created   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL,
  device     TEXT,
  created    INTEGER NOT NULL,
  last_seen  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS login_fail (
  k     TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  first INTEGER NOT NULL,
  until INTEGER NOT NULL
);

-- friends: one row per direction; both rows 'accepted' once accepted
CREATE TABLE IF NOT EXISTS friends (
  user_id   INTEGER NOT NULL,
  friend_id INTEGER NOT NULL,
  status    TEXT NOT NULL,
  created   INTEGER NOT NULL,
  PRIMARY KEY (user_id, friend_id)
);
CREATE INDEX IF NOT EXISTS friends_friend ON friends(friend_id);

-- one row per finished focus session
CREATE TABLE IF NOT EXISTS focus_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL,
  client_id  TEXT NOT NULL,
  start      INTEGER NOT NULL,
  end        INTEGER NOT NULL,
  planned_s  INTEGER NOT NULL,
  focus_s    INTEGER NOT NULL,
  verified_s INTEGER NOT NULL,
  phone_s    INTEGER NOT NULL,
  away_s     INTEGER NOT NULL,
  camera     INTEGER NOT NULL,
  completed  INTEGER NOT NULL,
  UNIQUE (user_id, client_id)
);
CREATE INDEX IF NOT EXISTS focus_log_user_start ON focus_log(user_id, start);

-- per-user screen time and focus state (replaces the legacy tables above)
CREATE TABLE IF NOT EXISTS udays (
  user_id INTEGER NOT NULL,
  device  TEXT NOT NULL,
  day     TEXT NOT NULL,
  data    TEXT NOT NULL,
  updated INTEGER NOT NULL,
  PRIMARY KEY (user_id, device, day)
);
CREATE INDEX IF NOT EXISTS udays_updated ON udays(user_id, updated);
CREATE TABLE IF NOT EXISTS ufocus (
  user_id INTEGER PRIMARY KEY,
  focus   INTEGER NOT NULL,
  paused  INTEGER NOT NULL,
  left_s  REAL NOT NULL,
  until   INTEGER NOT NULL,
  label   TEXT,
  updated INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
