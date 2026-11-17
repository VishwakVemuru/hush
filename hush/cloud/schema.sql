CREATE TABLE IF NOT EXISTS days (
  device  TEXT NOT NULL,
  day     TEXT NOT NULL,
  data    TEXT NOT NULL,
  updated INTEGER NOT NULL,
  PRIMARY KEY (device, day)
);
CREATE INDEX IF NOT EXISTS days_updated ON days(updated);
CREATE TABLE IF NOT EXISTS focus (
  id      INTEGER PRIMARY KEY,
  focus   INTEGER NOT NULL,
  paused  INTEGER NOT NULL,
  left_s  REAL NOT NULL,
  until   INTEGER NOT NULL,
  label   TEXT,
  updated INTEGER NOT NULL
);
