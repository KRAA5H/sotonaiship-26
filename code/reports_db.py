"""The reports database: one SQLite file built from dashboard/schema.sql.

The schema is the 11-column table in dashboard/SCHEMA.md, plus one column
added here: "area" - which of Southampton's 31 named areas (the Wikipedia
list of 30, plus Portswood) the report falls into, matched by
LocationService from the resident's GPS coordinates. The file is local to
the demo Mac and never committed (*.db is in .gitignore).

Run:
  python code/reports_db.py           create the file and load the synthetic reports if empty
  python code/reports_db.py --reset   delete the file first, then do the same
"""

import argparse
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "dashboard" / "schema.sql"
FAKE_REPORTS_PATH = ROOT / "dashboard" / "fake_reports.json"
# Named kerbside.db so it never collides with database.py's older reports.db.
DB_PATH = Path(os.getenv("DB_PATH") or Path(__file__).with_name("kerbside.db"))

COLUMNS = (
    "id", "created_at", "category_id", "status", "severity", "location", "area",
    "description", "has_photo", "duplicate_of", "reporter_ref", "link_token",
)
# What the council dashboard may see. reporter_ref never leaves the database.
COUNCIL_COLUMNS = tuple(c for c in COLUMNS if c != "reporter_ref")
STATUSES = ("new", "in_review", "resolved")
# The webhook threads and the website share one file, so a writer waits for
# the lock instead of failing with "database is locked".
BUSY_TIMEOUT_MS = 5000


def connect(path=None):
    """Autocommit connection; callers that need a transaction BEGIN one."""
    conn = sqlite3.connect(path or DB_PATH, isolation_level=None, check_same_thread=False,
                           timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    # WAL lets the dashboard read while the agent writes. It is stored in the
    # file, so this is a no-op after the first connection.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def council_reports(conn):
    """Every report for the dashboard, newest first, without reporter_ref."""
    rows = conn.execute(
        f"SELECT {', '.join(COUNCIL_COLUMNS)} FROM reports ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def set_status(conn, report_id, status):
    """Council action. Returns True if the report exists and was updated."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    cursor = conn.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))
    return cursor.rowcount == 1


def set_location(conn, report_id, location):
    """Fill in a street the resident sent after we had already logged the
    report. Kept exactly as before - unchanged - for whatever existing
    caller relies on setting just the free-text location on its own."""
    location = (location or "").strip()
    if not location or location.lower() == "not given":
        return False
    cursor = conn.execute("UPDATE reports SET location = ? WHERE id = ?",
                          (location, report_id))
    return cursor.rowcount == 1


def set_area(conn, report_id, area):
    """Fill in just the area, on its own - for a caller that already knows
    the area separately from the location string (e.g. a manual officer
    correction). Prefer set_location_and_area() below for the normal GPS
    link flow, where both values are known at the same moment."""
    area = (area or "").strip()
    if not area:
        return False
    cursor = conn.execute("UPDATE reports SET area = ? WHERE id = ?", (area, report_id))
    return cursor.rowcount == 1


def set_location_and_area(conn, report_id, location, area):
    """Sets location and area together, in one statement. This is the one
    to call from the GPS location-link flow: LocationService.reverse_geocode()
    returns both a street name and an area from the same lookup, so setting
    them with two separate calls (set_location() then set_area()) risks one
    succeeding and the other failing, leaving a report with a street but no
    area or vice versa. This function avoids that by updating both at once."""
    location = (location or "").strip()
    area = (area or "").strip()
    if not location and not area:
        return False
    cursor = conn.execute(
        "UPDATE reports SET location = COALESCE(NULLIF(?, ''), location), "
        "area = COALESCE(NULLIF(?, ''), area) WHERE id = ?",
        (location, area, report_id),
    )
    return cursor.rowcount == 1


def link_duplicate(conn, report_id, original_id):
    """Point a new report at an older one, used when a resolved job comes back."""
    if not report_id or not original_id or report_id == original_id:
        return False
    cursor = conn.execute(
        "UPDATE reports SET duplicate_of = ? WHERE id = ? AND duplicate_of IS NULL",
        (original_id, report_id),
    )
    return cursor.rowcount == 1


def latest_report_for(conn, reporter_ref):
    """That sender's most recent report, used to answer "any update?".
    area added alongside location, since a resident asking for an update
    deserves the same area context the dashboard shows officers."""
    if not reporter_ref:
        return None
    row = conn.execute(
        "SELECT id, created_at, category_id, status, severity, location, area, description, "
        "has_photo, duplicate_of, link_token FROM reports "
        "WHERE reporter_ref = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (reporter_ref,),
    ).fetchone()
    return dict(row) if row else None


def _ensure_area_column(conn):
    """Adds the area column to an existing database that predates it,
    without needing to touch schema.sql or delete the file. Safe to call
    on every start - does nothing once the column already exists. This is
    what was missing from this file before - the column needs to exist for
    every function above that references it to work at all."""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
    if "area" not in existing_columns:
        conn.execute("ALTER TABLE reports ADD COLUMN area TEXT")


def init_db(path=None, seed=True):
    """Create the table if missing, then load the synthetic reports if it is empty.

    Safe to call on every start. Returns the number of rows in reports.
    """
    conn = connect(path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reports'"
        ).fetchone()
        if not exists:
            # schema.sql has no IF NOT EXISTS, so only run it on a fresh file.
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        _ensure_area_column(conn)

        count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        if seed and count == 0:
            load_reports(conn, json.loads(FAKE_REPORTS_PATH.read_text(encoding="utf-8")))
            count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        return count
    finally:
        conn.close()


def load_reports(conn, reports):
    rows = []
    for report in reports:
        row = {column: report.get(column) for column in COLUMNS}
        # The JSON uses "" for "not a duplicate"; store NULL instead.
        row["duplicate_of"] = row["duplicate_of"] or None
        row["has_photo"] = int(bool(row["has_photo"]))
        rows.append(row)

    placeholders = ", ".join(f":{column}" for column in COLUMNS)
    conn.execute("BEGIN")
    try:
        conn.executemany(
            f"INSERT INTO reports ({', '.join(COLUMNS)}) VALUES ({placeholders})", rows
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# SUMMARY STATISTICS: plain counts and groupings for the dashboard. These
# describe what has already happened - they are not forecasts of future
# report volume, worth being precise about that distinction in the pitch.
# ---------------------------------------------------------------------------

def busiest_date(conn):
    """Returns {"date": "YYYY-MM-DD", "count": N} for the single day with
    the most reports received so far, or None if there are no reports yet."""
    row = conn.execute("""
        SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS count
        FROM reports
        GROUP BY date
        ORDER BY count DESC
        LIMIT 1
    """).fetchone()
    return dict(row) if row else None


def most_common_category(conn):
    """Returns {"category_id": ..., "count": N} for the most frequently
    reported issue type overall. Returns the raw category_id, same as
    council_reports does - map it to a human label with
    tools.category_labels() at the point you display it, not here."""
    row = conn.execute("""
        SELECT category_id, COUNT(*) AS count
        FROM reports
        GROUP BY category_id
        ORDER BY count DESC
        LIMIT 1
    """).fetchone()
    return dict(row) if row else None


def reports_by_area(conn):
    """Returns every area with its report count, busiest first. Reports
    with no matched area (e.g. the location link was never completed, or
    this row predates the area column) are grouped under 'Unknown' rather
    than silently dropped."""
    rows = conn.execute("""
        SELECT COALESCE(area, 'Unknown') AS area, COUNT(*) AS count
        FROM reports
        GROUP BY area
        ORDER BY count DESC
    """).fetchall()
    return [dict(row) for row in rows]


def main():
    parser = argparse.ArgumentParser(description="Create and seed the reports database")
    parser.add_argument("--reset", action="store_true", help="delete the database file first")
    args = parser.parse_args()

    if args.reset and DB_PATH.exists():
        DB_PATH.unlink()
    count = init_db()
    print(f"{DB_PATH}: {count} reports")


if __name__ == "__main__":
    main()
