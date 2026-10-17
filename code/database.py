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
                    street_name TEXT,
                    postcode TEXT,
                    area TEXT,
                    latitude REAL,
                    longitude REAL,
                    duplicate_of TEXT,
                    status TEXT,
                    routed_team TEXT,
                    created_at TEXT
                )
            """)

    def save_report(self, phone: str, transcript: str, category: str, severity: str,
                     confidence: str, street_name: Optional[str], postcode: Optional[str],
                     area: Optional[str], latitude: float, longitude: float,
                     duplicate_of: Optional[str] = None, status: str = "received",
                     routed_team: Optional[str] = None) -> str:
        """Creates a new report, returns its reference number (what the
        resident uses to check status later). street_name, postcode and
        area all come straight from LocationService.reverse_geocode() -
        the mandatory location link every resident goes through - never
        from anything they typed themselves. latitude/longitude are what
        the duplicate check actually calculates against; the other three
        are for humans reading the dashboard."""
        report_id = "REF-" + uuid.uuid4().hex[:6].upper()  # e.g. REF-A1B2C3

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO reports
                   (report_id, phone, transcript, category, severity, confidence,
                    street_name, postcode, area, latitude, longitude, duplicate_of,
                    status, routed_team, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (report_id, phone, transcript, category, severity, confidence,
                 street_name, postcode, area, latitude, longitude, duplicate_of,
                 status, routed_team, datetime.utcnow().isoformat()),
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
        """Returns the report_id of a likely duplicate, or None. Still runs
        on latitude/longitude, not area or street_name - two reports can
        share an area but be a kilometre apart, so coordinates stay the
        source of truth for this specific check."""
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

    # -----------------------------------------------------------------
    # SUMMARY STATISTICS: plain counts and groupings for the dashboard.
    # Descriptive, not predictive - they describe what has already
    # happened, not a forecast of future report volume.
    # -----------------------------------------------------------------

    def busiest_date(self) -> Optional[dict]:
        """Returns {"date": "YYYY-MM-DD", "count": N} for the single day
        with the most reports received so far."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS count
                FROM reports
                GROUP BY date
                ORDER BY count DESC
                LIMIT 1
            """).fetchone()
        return dict(row) if row else None

    def most_common_category(self) -> Optional[dict]:
        """Returns {"category": "pothole", "count": N} for the most
        frequently reported issue type overall."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT category, COUNT(*) AS count
                FROM reports
                GROUP BY category
                ORDER BY count DESC
                LIMIT 1
            """).fetchone()
        return dict(row) if row else None

    def reports_by_area(self) -> list[dict]:
        """Returns every area with its report count, busiest first.
        Reports with no matched area are grouped under 'Unknown' rather
        than silently dropped."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT COALESCE(area, 'Unknown') AS area, COUNT(*) AS count
                FROM reports
                GROUP BY area
                ORDER BY count DESC
            """).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# DEMO: creates the database, saves a couple of fake reports, reads them
# back, and runs the summary stats. Run this file directly to confirm it
# all works before wiring it into the rest of the pipeline.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    db = ReportDatabase("demo_reports.db")

    ref1 = db.save_report(
        phone="+44-SYNTHETIC-001", transcript="Big pothole on Shirley Road",
        category="pothole", severity="high", confidence="high",
        street_name="Shirley High Street", postcode="SO15 5LF", area="Shirley",
        latitude=50.9097, longitude=-1.4044, routed_team="Highways",
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

    print("\nSummary stats:")
    print("Busiest date:", db.busiest_date())
    print("Most common category:", db.most_common_category())
    print("Reports by area:", db.reports_by_area())
