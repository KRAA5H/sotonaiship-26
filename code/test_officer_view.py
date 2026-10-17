"""Tests for the officer's view (TODO-SPLIT Section 3): summary figures, the
stats CSV and the first-status-change time. Standard library plus Flask.

Run:
  python code/test_officer_view.py
"""

import base64
import csv
import io
import json
import re
import sqlite3
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reports_db
import tools
import website

FAKE = json.loads(reports_db.FAKE_REPORTS_PATH.read_text(encoding="utf-8"))
PASSWORD = "test-password"
AUTH = {"Authorization": "Basic " + base64.b64encode(f"officer:{PASSWORD}".encode()).decode()}
JSON_HEADERS = {**AUTH, "X-Requested-With": "kerbside"}


class Case(unittest.TestCase):
    def setUp(self):
        # save_report geocodes through Nominatim; keep tests off the network.
        patch = unittest.mock.patch.object(tools._location_service, "forward_geocode", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "officer.db"
        self.app = website.create_app(self.path, PASSWORD)
        self.client = self.app.test_client()
        self.conn = reports_db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def stats(self):
        return reports_db.summary_stats(self.conn)


class SummaryStatsTest(Case):
    def test_figures_match_the_synthetic_data(self):
        s = self.stats()
        open_rows = [r for r in FAKE if r["status"] in ("new", "in_review")]
        self.assertEqual(s["total"], len(FAKE))
        self.assertEqual(s["open"], len(open_rows))
        self.assertEqual(s["synthetic"], len(FAKE))
        self.assertEqual(s["with_photo"], sum(r["has_photo"] for r in FAKE))
        self.assertEqual(s["duplicates_caught"], sum(1 for r in FAKE if r["duplicate_of"]))
        self.assertEqual(sum(s["open_by_severity"].values()), len(open_rows))
        self.assertEqual(sum(s["open_by_category"].values()), len(open_rows))
        self.assertEqual(s["open_by_severity"]["high"], sum(r["severity"] == "high" for r in open_rows))

    def test_average_time_to_first_change(self):
        changed = [r for r in FAKE if r["status_changed_at"]]
        hours = [(datetime.fromisoformat(r["status_changed_at"]) - datetime.fromisoformat(r["created_at"]))
                 .total_seconds() / 3600 for r in changed]
        s = self.stats()
        self.assertEqual(s["first_change_count"], len(changed))
        self.assertAlmostEqual(s["first_change_avg_hours"], round(sum(hours) / len(hours), 1))

    def test_no_changes_means_no_average(self):
        self.conn.execute("UPDATE reports SET status_changed_at = NULL")
        self.assertIsNone(self.stats()["first_change_avg_hours"])
        self.assertEqual(self.stats()["first_change_count"], 0)

    def test_counts_follow_the_database_not_a_constant(self):
        before = self.stats()
        tools.save_report("pothole", "1 Count Road", "Hole", severity="high", has_photo=True, conn=self.conn)
        after = self.stats()
        self.assertEqual(after["total"], before["total"] + 1)
        self.assertEqual(after["open"], before["open"] + 1)
        self.assertEqual(after["with_photo"], before["with_photo"] + 1)
        self.assertEqual(after["open_by_severity"]["high"], before["open_by_severity"]["high"] + 1)
        self.assertEqual(after["synthetic"], before["synthetic"])

    def test_missing_severity_is_counted_as_not_set(self):
        tools.save_report("pothole", "2 Count Road", "Hole", conn=self.conn)
        self.assertEqual(self.stats()["open_by_severity"]["not set"], 1)


class FirstStatusChangeTest(Case):
    def new_report(self):
        return tools.save_report("pothole", "3 Change Road", "Hole", conn=self.conn)["report_id"]

    def changed_at(self, report_id):
        return self.conn.execute("SELECT status_changed_at FROM reports WHERE id = ?",
                                 (report_id,)).fetchone()[0]

    def test_set_on_the_first_real_change_only(self):
        rid = self.new_report()
        self.assertIsNone(self.changed_at(rid))
        reports_db.set_status(self.conn, rid, "new")  # no change
        self.assertIsNone(self.changed_at(rid))
        reports_db.set_status(self.conn, rid, "in_review")
        first = self.changed_at(rid)
        self.assertIsNotNone(first)
        datetime.fromisoformat(first)
        reports_db.set_status(self.conn, rid, "resolved")
        self.assertEqual(self.changed_at(rid), first)

    def test_council_button_records_it_and_the_figures_move(self):
        rid = self.new_report()
        before = self.stats()["first_change_count"]
        response = self.client.post(f"/council/reports/{rid}/status", json={"status": "resolved"},
                                    headers=JSON_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self.changed_at(rid))
        polled = self.client.get("/council/reports.json", headers=AUTH).get_json()["stats"]
        self.assertEqual(polled["first_change_count"], before + 1)

    def test_old_database_gains_the_column(self):
        old = Path(self.tmp.name) / "old.db"
        raw = sqlite3.connect(old)
        try:
            # The original 11-column table, before area and status_changed_at existed.
            raw.execute("CREATE TABLE reports (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
                        "category_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', severity TEXT, "
                        "location TEXT, description TEXT, has_photo INTEGER NOT NULL DEFAULT 0, "
                        "duplicate_of TEXT, reporter_ref TEXT, link_token TEXT UNIQUE NOT NULL)")
            raw.commit()
        finally:
            raw.close()
        reports_db.init_db(old, seed=False)
        conn = reports_db.connect(old)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
        conn.close()
        self.assertIn("status_changed_at", columns)


class CouncilPageTest(Case):
    def page(self):
        return self.client.get("/council", headers=AUTH).get_data(as_text=True)

    def test_figures_are_on_the_page(self):
        html = self.page()
        blob = re.search(r'<script type="application/json" id="stats">(.*?)</script>', html, re.S)
        self.assertEqual(json.loads(blob.group(1)), self.stats())
        self.assertIn("Key figures", html)
        self.assertIn("synthetic demo data", html)

    def test_rows_are_flagged_synthetic_without_the_reference(self):
        tools.save_report("pothole", "4 Flag Road", "Hole", reporter="+447700900123", conn=self.conn)
        tools.save_report("pothole", "5 Flag Road", "Hole", conn=self.conn)
        reports = self.client.get("/council/reports.json", headers=AUTH).get_json()["reports"]
        flags = {r["location"]: r["synthetic"] for r in reports}
        self.assertEqual(flags["4 Flag Road"], 0)
        self.assertEqual(flags["5 Flag Road"], 0)
        self.assertTrue(all(r["synthetic"] for r in reports if r["id"] in {f["id"] for f in FAKE}))
        body = json.dumps(reports)
        self.assertNotIn("reporter_ref", body)
        self.assertNotIn("synthetic-", body)


class StatsCsvTest(Case):
    URL = "/council/stats.csv"

    def rows(self):
        response = self.client.get(self.URL, headers=AUTH)
        self.assertEqual(response.status_code, 200)
        return response, {r["metric"]: r for r in csv.DictReader(io.StringIO(response.get_data(as_text=True)))}

    def test_needs_the_password(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_same_figures_as_the_page(self):
        response, rows = self.rows()
        s = self.stats()
        self.assertTrue(response.mimetype == "text/csv")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(int(rows["total_reports"]["value"]), s["total"])
        self.assertEqual(int(rows["open_reports"]["value"]), s["open"])
        self.assertEqual(int(rows["synthetic_reports"]["value"]), s["synthetic"])
        self.assertEqual(int(rows["duplicates_caught"]["value"]), s["duplicates_caught"])
        self.assertEqual(int(rows["reports_with_photo"]["value"]), s["with_photo"])
        self.assertEqual(float(rows["avg_hours_to_first_status_change"]["value"]), s["first_change_avg_hours"])
        for cid, n in s["open_by_category"].items():
            self.assertEqual(int(rows[f"open_category_{cid}"]["value"]), n)
            self.assertEqual(rows[f"open_category_{cid}"]["label"], tools.category_labels()[cid])
        datetime.fromisoformat(rows["generated_at"]["value"])

    def test_never_contains_reporter_ref(self):
        body = self.client.get(self.URL, headers=AUTH).get_data(as_text=True)
        self.assertNotIn("reporter_ref", body)
        self.assertNotIn("synthetic-", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
