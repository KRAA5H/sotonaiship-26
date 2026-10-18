"""Made-up reports for the tests only.

REPORTS is 68 invented rows (reporter_ref "test-..."). seed() loads them into a
test's own temporary database. Nothing here is read by the site, the agent or
kerbside.db.
"""

import json
from pathlib import Path

import reports_db

REPORTS = json.loads(Path(__file__).with_name("reports.json").read_text(encoding="utf-8"))


def seed(path):
    """Create the database at path and load REPORTS. Returns the row count."""
    reports_db.init_db(path)
    conn = reports_db.connect(path)
    try:
        reports_db.load_reports(conn, REPORTS)
        return conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    finally:
        conn.close()
