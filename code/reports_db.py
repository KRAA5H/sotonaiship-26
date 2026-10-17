"""The reports database: one SQLite file built from dashboard/schema.sql.

The schema is the 11-column table in dashboard/SCHEMA.md. The file is local to
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
    "id", "created_at", "category_id", "status", "severity", "location",
    "description", "has_photo", "duplicate_of", "reporter_ref", "link_token",
)


def connect(path=None):
    """Autocommit connection; callers that need a transaction BEGIN one."""
    conn = sqlite3.connect(path or DB_PATH, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


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
