"""The reports database: one SQLite file built from dashboard/schema.sql.

The schema is the table in dashboard/SCHEMA.md: the 11 report columns, the two
photo reference columns, source and source_url (internal only), and "area", which of Southampton's 31 named areas
(the Wikipedia list of 30, plus Portswood) the report falls into, matched by
LocationService from the resident's GPS coordinates. The file is local to the
demo Mac and never committed (*.db is in .gitignore).

Run:
  python code/reports_db.py           create the file (empty) if it is missing
  python code/reports_db.py --reset   delete the file first, then create it empty

Real reports are loaded by code/import_fixmystreet.py; the agent adds its own.
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "dashboard" / "schema.sql"
# Named kerbside.db so it never collides with database.py's older reports.db.
DB_PATH = Path(os.getenv("DB_PATH") or Path(__file__).with_name("kerbside.db"))

COLUMNS = (
    "id", "created_at", "category_id", "status", "capture_state", "routing_status",
    "severity", "location", "area",
    "description", "has_photo", "photo_guid", "photo_mime", "duplicate_of",
    "reporter_ref", "link_token", "status_changed_at", "photo_features",
    "source", "source_url",
)
# What the council dashboard may see. reporter_ref never leaves the database,
# and neither does the attachment guid: it is a key to the resident's photo, not
# something the dashboard reads. The page gets photo_stored instead and asks the
# password-protected /council/photos/<id> route for the image.
# source and source_url are internal: imported rows look like any other row.
COUNCIL_COLUMNS = tuple(c for c in COLUMNS
                        if c not in ("reporter_ref", "photo_guid", "photo_mime", "source", "source_url"))
STATUSES = ("new", "in_review", "resolved")
# The webhook threads and the website share one file, so a writer waits for
# the lock instead of failing with "database is locked".
BUSY_TIMEOUT_MS = 5000
# Added after the first reports table was built and populated, so init_db adds
# them to an existing file instead of relying on schema.sql alone.
PHOTO_COLUMNS = (("photo_guid", "TEXT"), ("photo_mime", "TEXT"))
# D51: capture and routing are policy-owned and default to the honest state.
POLICY_COLUMNS = (("capture_state", "TEXT NOT NULL DEFAULT 'captured'"),
                  ("routing_status", "TEXT NOT NULL DEFAULT 'needs_review'"))
# Where a row came from: our agent, or an imported FixMyStreet report. Internal only.
SOURCE_COLUMNS = (("source", "TEXT NOT NULL DEFAULT 'agent'"), ("source_url", "TEXT"))


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
    """Every report for the dashboard, newest first, without reporter_ref.

    An imported report has no resident to send a link to, so its link_token
    comes back empty and the page shows no resident view for it. Nothing
    else about the row says where it came from.
    """
    columns = [c if c != "link_token" else
               "CASE WHEN source = 'fixmystreet' THEN NULL ELSE link_token END AS link_token"
               for c in COUNCIL_COLUMNS]
    rows = conn.execute(
        f"SELECT {', '.join(columns)}, "
        # A photo the dashboard can show is one BlueBubbles holds (photo_guid).
        "COALESCE(photo_guid, '') != '' AS photo_stored "
        "FROM reports ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def set_status(conn, report_id, status):
    """Council action. Returns True if the report exists and was updated."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    # status_changed_at records the FIRST real change only, for "time to first
    # action". SQLite evaluates every SET expression against the old row.
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cursor = conn.execute(
        "UPDATE reports SET status_changed_at = CASE WHEN status_changed_at IS NULL AND status != ? "
        "THEN ? ELSE status_changed_at END, status = ? WHERE id = ?",
        (status, now, status, report_id),
    )
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


def set_photo(conn, report_id, guid, mime):
    """Attach a photo the resident sent after the report was saved, exactly once.

    The `photo_guid IS NULL` guard makes a replayed webhook a no-op instead of an
    overwrite. Returns True only if this call is the one that attached it.
    """
    if not report_id or not guid:
        return False
    cursor = conn.execute(
        "UPDATE reports SET photo_guid = ?, photo_mime = ?, has_photo = 1 "
        "WHERE id = ? AND (photo_guid IS NULL OR photo_guid = '')",
        (guid, mime, report_id),
    )
    return cursor.rowcount == 1


def open_reports_for(conn, reporter_ref, limit=3):
    """That sender's unresolved reports still without a photo, newest first.

    The candidates for a photo sent on its own, after the report was saved. The id
    is here so the caller can attach to it; it never reaches the resident.
    """
    if not reporter_ref:
        return []
    rows = conn.execute(
        "SELECT id, created_at, category_id, location, link_token FROM reports "
        "WHERE reporter_ref = ? AND status <> 'resolved' "
        "AND (photo_guid IS NULL OR photo_guid = '') "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        (reporter_ref, limit),
    ).fetchall()
    return [dict(row) for row in rows]


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


def _ensure_column(conn, name):
    """Adds a nullable TEXT column to a database that predates it. Safe on every start."""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
    if name not in existing_columns:
        conn.execute(f"ALTER TABLE reports ADD COLUMN {name} TEXT")


def set_photo_features(conn, report_id, raw):
    """Store a photo's structured features, validated against photo_features.

    Returns (stored, problems). Nothing is stored unless the features fit the
    shape; a location in the model's reply is never stored.
    """
    import photo_features  # noqa: PLC0415
    features, problems = photo_features.validate(raw)
    if features is None:
        return False, problems
    cursor = conn.execute("UPDATE reports SET photo_features = ? WHERE id = ?",
                          (json.dumps(features), report_id))
    return cursor.rowcount == 1, problems


def council_photo_source(conn, report_id):
    """What the council photo route needs to find one report's photo, or None.

    photo_guid/photo_mime point at the resident's photo in BlueBubbles.
    """
    row = conn.execute(
        "SELECT photo_guid, photo_mime, category_id, has_photo FROM reports WHERE id = ?",
        (report_id,),
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


def init_db(path=None):
    """Create the table if missing and migrate it. Never adds rows.

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
        _add_photo_columns(conn)
        _add_policy_columns(conn)
        _add_columns(conn, SOURCE_COLUMNS)

        _ensure_area_column(conn)
        for column in ("status_changed_at", "photo_features"):
            _ensure_column(conn, column)

        return conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    finally:
        conn.close()


def _add_photo_columns(conn):
    """Additive migration for a file built before the photo reference columns.

    Idempotent: it reads PRAGMA table_info and only adds what is missing, so a
    fresh file from schema.sql and a 36-photo legacy file both end up the same.
    """
    present = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
    for name, kind in PHOTO_COLUMNS:
        if name in present:
            continue
        try:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {name} {kind}")
        except sqlite3.OperationalError as error:
            # A second process added the column between the check and the ALTER.
            if "duplicate column" not in str(error).lower():
                raise


def _add_columns(conn, columns):
    """Additive migration: add any of these (name, type) columns that are missing."""
    present = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
    for name, kind in columns:
        if name in present:
            continue
        try:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {name} {kind}")
        except sqlite3.OperationalError as error:
            if "duplicate column" not in str(error).lower():
                raise


def _add_policy_columns(conn):
    """Additive D51 migration: capture_state and routing_status, with defaults.

    Idempotent, like _add_photo_columns, so a fresh schema.sql and an older file
    end up the same after one start.
    """
    present = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
    for name, kind in POLICY_COLUMNS:
        if name in present:
            continue
        try:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {name} {kind}")
        except sqlite3.OperationalError as error:
            if "duplicate column" not in str(error).lower():
                raise


def load_reports(conn, reports):
    rows = []
    for report in reports:
        row = {column: report.get(column) for column in COLUMNS}
        # The JSON uses "" for "not a duplicate"; store NULL instead.
        row["duplicate_of"] = row["duplicate_of"] or None
        row["status_changed_at"] = row["status_changed_at"] or None
        row["photo_features"] = row["photo_features"] or None
        row["capture_state"] = row["capture_state"] or "captured"
        row["routing_status"] = row["routing_status"] or "needs_review"
        row["has_photo"] = int(bool(row["has_photo"]))
        row["source"] = row["source"] or "agent"
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


OPEN_STATUSES = ("new", "in_review")


def summary_stats(conn):
    """The figures for the strip above the council list and /council/stats.csv.

    Computed from the database on every call, never stored or hardcoded.
    "Open" means new or in review. Time to first status change is measured
    only on reports whose status has changed at least once.
    """
    rows = conn.execute(
        "SELECT category_id, status, severity, has_photo, duplicate_of, created_at, status_changed_at "
        "FROM reports"
    ).fetchall()
    open_rows = [r for r in rows if r["status"] in OPEN_STATUSES]

    by_severity = {level: 0 for level in ("high", "medium", "low", "not set")}
    by_category = {}
    for r in open_rows:
        by_severity[r["severity"] if r["severity"] in by_severity else "not set"] += 1
        by_category[r["category_id"]] = by_category.get(r["category_id"], 0) + 1

    waits = [
        (datetime.fromisoformat(r["status_changed_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds() / 3600
        for r in rows if r["status_changed_at"]
    ]
    return {
        "total": len(rows),
        "open": len(open_rows),
        "open_by_severity": by_severity,
        "open_by_category": dict(sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))),
        "with_photo": sum(r["has_photo"] for r in rows),
        "duplicates_caught": sum(1 for r in rows if r["duplicate_of"]),
        "first_change_count": len(waits),
        "first_change_avg_hours": round(sum(waits) / len(waits), 1) if waits else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Create the reports database")
    parser.add_argument("--reset", action="store_true", help="delete the database file first")
    args = parser.parse_args()

    if args.reset and DB_PATH.exists():
        DB_PATH.unlink()
    count = init_db()
    print(f"{DB_PATH}: {count} reports")


if __name__ == "__main__":
    main()
