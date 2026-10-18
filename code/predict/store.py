"""predict.db: everything the forecast writes, kept apart from the bot's database.

Every row carries the run id, when it was made and whether it rests on
synthetic data. The dashboard reads only these tables, so a page load never
retrains anything.
"""

import json
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS pred_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
    kind TEXT NOT NULL, status TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 1,
    forecast_week TEXT, sources TEXT, metrics TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS pred_forecasts (
    run_id INTEGER NOT NULL, created_at TEXT NOT NULL, week TEXT NOT NULL, street TEXT NOT NULL,
    area TEXT, category TEXT NOT NULL, expected REAL, low INTEGER, high INTEGER, baseline REAL,
    r13 INTEGER, rate REAL, confidence TEXT, drivers TEXT, synthetic INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pred_forecasts_run ON pred_forecasts(run_id);
CREATE TABLE IF NOT EXISTS pred_surges (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, detected_at TEXT NOT NULL,
    street TEXT NOT NULL, area TEXT, category TEXT NOT NULL, window_h INTEGER, count INTEGER,
    expected REAL, weekly_rate REAL, p_value REAL, fixed_rule INTEGER, synthetic INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pred_actions (
    key TEXT PRIMARY KEY, run_id INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    driver TEXT NOT NULL, driver_key TEXT, action TEXT NOT NULL, team TEXT, area TEXT, streets TEXT,
    categories TEXT, expected_date TEXT, do_by TEXT, steps TEXT, reasons TEXT, confidence TEXT,
    volume REAL, volume_low INTEGER, volume_high INTEGER, harm REAL, urgency REAL, conf_weight REAL,
    score REAL, status TEXT NOT NULL DEFAULT 'proposed', dismiss_reason TEXT, synthetic INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pred_action_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, at TEXT NOT NULL,
    from_status TEXT, to_status TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS pred_outcomes (
    run_id INTEGER NOT NULL, recorded_at TEXT NOT NULL, week TEXT NOT NULL, street TEXT NOT NULL,
    category TEXT NOT NULL, predicted REAL, baseline REAL, actual INTEGER, source TEXT,
    synthetic INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pred_uplift (
    run_id INTEGER NOT NULL, driver TEXT, category TEXT, after REAL, normal REAL, uplift REAL,
    n_events INTEGER, confidence TEXT, synthetic INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pred_events (
    run_id INTEGER NOT NULL, event_id TEXT, name TEXT, type TEXT, start_date TEXT, end_date TEXT,
    venue TEXT, areas TEXT, coverage TEXT, outside_council TEXT, status TEXT, source_url TEXT,
    collected_on TEXT, synthetic INTEGER NOT NULL
);
"""

STATUSES = ("proposed", "approved", "scheduled", "done", "dismissed")
NEXT = {"proposed": ("approved", "dismissed"), "approved": ("scheduled", "done", "dismissed"),
        "scheduled": ("done", "dismissed"), "done": (), "dismissed": ()}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None):
    conn = sqlite3.connect(path or config.PREDICT_DB, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def start_run(conn, kind):
    cur = conn.execute("INSERT INTO pred_runs (started_at, kind, status) VALUES (?, ?, 'running')", (now(), kind))
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id, status, synthetic=1, forecast_week=None, sources=None, metrics=None, error=None):
    conn.execute("UPDATE pred_runs SET finished_at = ?, status = ?, synthetic = ?, forecast_week = ?, "
                 "sources = ?, metrics = ?, error = ? WHERE id = ?",
                 (now(), status, synthetic, forecast_week, json.dumps(sources or []),
                  json.dumps(metrics or {}, default=str), error, run_id))
    conn.commit()


def latest_run(conn, kind="batch", ok_only=True):
    sql = "SELECT * FROM pred_runs WHERE kind = ?" + (" AND status = 'ok'" if ok_only else "")
    row = conn.execute(sql + " ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
    return dict(row) if row else None


def save_forecasts(conn, run_id, rows):
    stamp = now()
    conn.executemany(
        "INSERT INTO pred_forecasts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, stamp, r["week"], r["street"], r["area"], r["category"], r["expected"], r["low"], r["high"],
          r["baseline"], r["r13"], r["rate"], r["confidence"], json.dumps(r["drivers"]), r["synthetic"])
         for r in rows])


def save_surges(conn, run_id, rows):
    stamp = now()
    conn.executemany(
        "INSERT INTO pred_surges (run_id, detected_at, street, area, category, window_h, count, expected, "
        "weekly_rate, p_value, fixed_rule, synthetic) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, stamp, r["street"], r["area"], r["category"], r["window_h"], r["count"], r["expected"],
          r["weekly_rate"], r["p_value"], int(r["fixed_rule"]), r["synthetic"]) for r in rows])


def save_actions(conn, run_id, plans):
    """Upsert by key: a re-run refreshes the numbers but never resets an officer's decision."""
    stamp = now()
    for p in plans:
        conn.execute(
            """INSERT INTO pred_actions (key, run_id, created_at, updated_at, driver, driver_key, action, team,
                   area, streets, categories, expected_date, do_by, steps, reasons, confidence, volume,
                   volume_low, volume_high, harm, urgency, conf_weight, score, status, synthetic)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)
               ON CONFLICT(key) DO UPDATE SET run_id = excluded.run_id, updated_at = excluded.updated_at,
                   streets = excluded.streets, categories = excluded.categories, reasons = excluded.reasons,
                   confidence = excluded.confidence, volume = excluded.volume, volume_low = excluded.volume_low,
                   volume_high = excluded.volume_high, harm = excluded.harm, urgency = excluded.urgency,
                   conf_weight = excluded.conf_weight, score = excluded.score, do_by = excluded.do_by""",
            (p["key"], run_id, stamp, stamp, p["driver"], p["driver_key"], p["action"], p["team"], p["area"],
             json.dumps(p["streets"]), json.dumps(p["categories"]), p["expected_date"], p["do_by"],
             json.dumps(p["steps"]), json.dumps(p["reasons"]), p["confidence"], p["volume"], p["volume_low"],
             p["volume_high"], p["harm"], p["urgency"], p["conf_weight"], p["score"], p["synthetic"]))


def set_action_status(conn, key, status, note=None):
    """Officer decision. Returns (ok, message). Every change is written to the audit table."""
    row = conn.execute("SELECT status FROM pred_actions WHERE key = ?", (key,)).fetchone()
    if row is None:
        return False, "no such plan"
    if status not in NEXT.get(row["status"], ()):
        return False, f"cannot go from {row['status']} to {status}"
    if status == "dismissed" and not (note or "").strip():
        return False, "a reason is needed to dismiss a plan"
    stamp = now()
    conn.execute("UPDATE pred_actions SET status = ?, updated_at = ?, dismiss_reason = ? WHERE key = ?",
                 (status, stamp, (note or "").strip()[:300] if status == "dismissed" else None, key))
    conn.execute("INSERT INTO pred_action_audit (key, at, from_status, to_status, note) VALUES (?, ?, ?, ?, ?)",
                 (key, stamp, row["status"], status, (note or "").strip()[:300] or None))
    conn.commit()
    return True, status


def save_outcomes(conn, run_id, rows, source):
    stamp = now()
    conn.executemany("INSERT INTO pred_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     [(run_id, stamp, str(r["week"]), r["street"], r["category"], r.get("predicted"),
                       r.get("baseline"), int(r["actual"]), source, r["synthetic"]) for r in rows])


def save_uplift(conn, run_id, rows, synthetic):
    conn.executemany("INSERT INTO pred_uplift VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     [(run_id, r["driver"], r["category"], r["after"], r["normal"], r["uplift"], r["n_events"],
                       r["confidence"], synthetic) for r in rows])


def save_events(conn, run_id, events):
    conn.executemany("INSERT INTO pred_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     [(run_id, e["id"], e["name"], e["type"], str(e["start"]), str(e["end"]), e["venue"],
                       json.dumps(list(e["areas"])), e["coverage"], e["outside_council"], e["status"],
                       e["source_url"], e["collected_on"], e["synthetic"]) for e in events])
