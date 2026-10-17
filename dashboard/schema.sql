-- reports: one row per resident report
CREATE TABLE reports (
  id            TEXT PRIMARY KEY,                -- R-0001
  created_at    TEXT NOT NULL,                   -- 2026-10-17T12:00:00Z
  category_id   TEXT NOT NULL,                   -- from categories.json
  status        TEXT NOT NULL DEFAULT 'new',     -- new | in_review | resolved
  severity      TEXT,                            -- high | medium | low
  location      TEXT,                            -- street or address, as the resident said it
  description   TEXT,                            -- what is wrong
  has_photo     INTEGER NOT NULL DEFAULT 0,      -- 0 or 1
  duplicate_of  TEXT,                            -- id of the first report, if a repeat
  reporter_ref  TEXT,                            -- anonymous reference, never a real number
  link_token    TEXT UNIQUE NOT NULL,            -- long random string for the resident's page /r/<token>
  area          TEXT,                            -- named Southampton area, from LocationService (may be empty)
  status_changed_at TEXT                         -- when the status FIRST changed, for time to first action
);
