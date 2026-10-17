import sqlite3
import uuid
from datetime import datetime
from typing import Optional


class ReportDatabase:
    def __init__(self, db_path: str = "reports.db"):
        self.db_path = db_path
        self._create_table_if_missing()

    def _connect(self):
        # check_same_thread=False because Flask may call this from a
        # different thread than the one that created the connection
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _create_table_if_missing(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    phone TEXT,
                    transcript TEXT,
                    category TEXT,
                    severity TEXT,
                    confidence TEXT,
                    location TEXT,
                    latitude REAL,
                    longitude REAL,
                    duplicate_of TEXT,
                    status TEXT,
                    routed_team TEXT,
                    created_at TEXT
                )
            """)

    def save_report(self, phone: str, transcript: str, category: str, severity: str,
                     confidence: str, location: str, latitude: float, longitude: float,
                     duplicate_of: Optional[str] = None, status: str = "received",
                     routed_team: Optional[str] = None) -> str:
        """Creates a new report, returns its reference number (what the
        resident uses to check status later)."""
        report_id = "REF-" + uuid.uuid4().hex[:6].upper()  # e.g. REF-A1B2C3

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reports
                   (report_id, phone, transcript, category, severity, confidence,
                    location, latitude, longitude, duplicate_of, status, routed_team, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (report_id, phone, transcript, category, severity, confidence,
                 location, latitude, longitude, duplicate_of, status, routed_team,
                 datetime.utcnow().isoformat()),
            )
        return report_id

    def get_report(self, report_id: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row  # lets us read columns by name
            row = conn.execute(
                "SELECT * FROM reports WHERE report_id = ?", (report_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_reports(self) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def update_status(self, report_id: str, new_status: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE reports SET status = ? WHERE report_id = ?",
                (new_status, report_id),
            )

    def find_nearby_same_category(self, category: str, latitude: float, longitude: float,
                                   distance_threshold_m: float = 50.0) -> Optional[str]:
        """Returns the report_id of a likely duplicate, or None. Pulls every
        report of the same category and checks distance in Python - fine at
        this scale, no need for a spatial SQL extension."""
        import math

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            candidates = conn.execute(
                "SELECT report_id, latitude, longitude FROM reports WHERE category = ?",
                (category,),
            ).fetchall()

        lat_m = 111_000
        lon_m = 111_000 * math.cos(math.radians(latitude))

        for row in candidates:
            dx = (row["longitude"] - longitude) * lon_m
            dy = (row["latitude"] - latitude) * lat_m
            if math.sqrt(dx ** 2 + dy ** 2) <= distance_threshold_m:
                return row["report_id"]
        return None


# ---------------------------------------------------------------------------
# DEMO: creates the database, saves a couple of fake reports, reads them
# back. Run this file directly to confirm it all works before wiring it
# into the rest of the pipeline.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    db = ReportDatabase("demo_reports.db")

    ref1 = db.save_report(
        phone="+44-SYNTHETIC-001", transcript="Big pothole on Shirley Road",
        category="pothole", severity="high", confidence="high",
        location="Shirley Road", latitude=50.9097, longitude=-1.4044,
        routed_team="Highways",
    )
    print(f"Saved report: {ref1}")

    print("\nLooking it up:")
    print(db.get_report(ref1))

    print("\nChecking for a duplicate nearby:")
    duplicate = db.find_nearby_same_category("pothole", 50.9098, -1.4045)
    print(f"Duplicate found: {duplicate}")

    print("\nMarking it resolved:")
    db.update_status(ref1, "resolved")
    print(db.get_report(ref1))

    print("\nAll reports:")
    for report in db.list_reports():
        print(report)