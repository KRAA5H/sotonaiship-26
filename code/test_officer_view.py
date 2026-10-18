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

from fixtures import REPORTS as FAKE, seed as seed_fixtures  # noqa: E402
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
        seed_fixtures(self.path)
        self.app = website.create_app(self.path, PASSWORD)
        self.client = self.app.test_client()
        self.conn = reports_db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def stats(self):
        return reports_db.summary_stats(self.conn)


class SummaryStatsTest(Case):
    def test_figures_match_the_fixture_data(self):
        s = self.stats()
        open_rows = [r for r in FAKE if r["status"] in ("new", "in_review")]
        self.assertEqual(s["total"], len(FAKE))
        self.assertEqual(s["open"], len(open_rows))
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
        reports_db.init_db(old)
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
        self.assertNotIn("synthetic", html.lower())
        self.assertIn("Report data: mySociety FixMyStreet (ODC-BY)", html)

    def test_rows_carry_no_reference_and_no_source(self):
        tools.save_report("pothole", "4 Flag Road", "Hole", reporter="+447700900123", conn=self.conn)
        reports = self.client.get("/council/reports.json", headers=AUTH).get_json()["reports"]
        body = json.dumps(reports)
        for key in ("reporter_ref", "source", "source_url", "synthetic"):
            self.assertNotIn(f'"{key}"', body)
        for fake in FAKE:
            self.assertNotIn(fake["reporter_ref"], body)


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
        for fake in FAKE:
            self.assertNotIn(fake["reporter_ref"], body)


class PhotoTest(Case):
    GUID = "iMessage;-;at-0-TESTGUID"
    PNG = bytes.fromhex("89504e470d0a1a0a") + b"-real-photo-bytes"

    def unstored_photo_id(self):
        """A row that says a photo was sent but holds no photo reference."""
        return next(r["id"] for r in FAKE if r["has_photo"])

    def no_photo_id(self):
        return next(r["id"] for r in FAKE if not r["has_photo"])

    def real_report(self, guid=GUID, mime="image/jpeg"):
        rid = tools.save_report("pothole", "6 Photo Road", "Hole", reporter="+447700900123",
                                conn=self.conn)["report_id"]
        if guid:
            self.assertTrue(reports_db.set_photo(self.conn, rid, guid, mime))
        return rid

    def get(self, rid, **kwargs):
        return self.client.get(f"/council/photos/{rid}", headers=AUTH, **kwargs)

    def test_needs_the_password(self):
        self.assertEqual(self.client.get(f"/council/photos/{self.unstored_photo_id()}").status_code, 401)

    def test_a_photo_that_was_never_stored_is_a_404(self):
        # No placeholder images any more: without a BlueBubbles guid there is nothing to show.
        never_called = unittest.mock.patch.object(website.bb, "download_attachment",
                                                  side_effect=AssertionError("no fetch expected"))
        with never_called:
            self.assertEqual(self.get(self.unstored_photo_id()).status_code, 404)

    def test_real_photo_comes_from_bluebubbles(self):
        rid = self.real_report()
        with unittest.mock.patch.object(website.bb, "download_attachment",
                                        return_value=(self.PNG, "image/jpeg")) as download:
            response = self.get(rid)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(), self.PNG)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(download.call_args.args[0], self.GUID)
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn(self.GUID, str(response.headers))

    def test_refuses_anything_that_is_not_an_image(self):
        rid = self.real_report(mime="text/html")
        with unittest.mock.patch.object(website.bb, "download_attachment",
                                        return_value=(b"<script>", "text/html")):
            self.assertEqual(self.get(rid).status_code, 404)
        with unittest.mock.patch.object(website.bb, "download_attachment", return_value=None):
            self.assertEqual(self.get(self.real_report(guid="iMessage;-;other")).status_code, 404)

    def test_no_photo_is_a_404(self):
        never_called = unittest.mock.patch.object(website.bb, "download_attachment",
                                                  side_effect=AssertionError("no fetch expected"))
        with never_called:
            for rid in (self.no_photo_id(), "R-9999", self.real_report(guid=None)):
                self.assertEqual(self.get(rid).status_code, 404, rid)

    def test_real_report_without_a_guid_is_not_shown_as_stored(self):
        rid = self.real_report(guid=None)
        self.conn.execute("UPDATE reports SET has_photo = 1 WHERE id = ?", (rid,))
        reports = {r["id"]: r for r in self.client.get("/council/reports.json", headers=AUTH).get_json()["reports"]}
        self.assertEqual(reports[rid]["has_photo"], 1)
        self.assertFalse(reports[rid]["photo_stored"])
        self.assertIn("Photo sent, not stored", self.client.get("/council", headers=AUTH).get_data(as_text=True))

    def test_photos_are_not_in_the_public_static_folder(self):
        for path in ("/assets/photos/synthetic/pothole.png", "/assets/../photos/synthetic/pothole.png",
                     "/photos/synthetic/pothole.png"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertFalse((website.WEB_DIR / "static" / "photos").exists())

    def test_page_gets_a_flag_never_the_guid(self):
        rid = self.real_report()
        reports = self.client.get("/council/reports.json", headers=AUTH).get_json()["reports"]
        for r in reports:
            self.assertNotIn("photo_guid", r)
            self.assertNotIn("photo_mime", r)
        flags = {r["id"]: r["photo_stored"] for r in reports}
        self.assertTrue(flags[rid])
        for fake in FAKE:
            self.assertFalse(flags[fake["id"]], fake["id"])
        page = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        self.assertNotIn(self.GUID, page)
        self.assertNotIn(self.GUID, json.dumps(reports))

    def test_page_labels_words_and_model_text_apart(self):
        html = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        self.assertIn("Resident's words", html)
        self.assertIn("AI-generated description", html)
        self.assertIn("not an officer's note", html)
        self.assertIn("No photo", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
