"""Tests for import_fixmystreet.py. Offline: a small made-up feed and geocode cache
in a temp folder, and any network call fails the test.

Run: python code/test_import_fixmystreet.py
"""

import base64
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import import_fixmystreet as fms  # noqa: E402
import reports_db  # noqa: E402
import tools  # noqa: E402
import website  # noqa: E402

AUTH = {"Authorization": "Basic " + base64.b64encode(b"officer:pw").decode()}


def item(n, service, when, lat="50.92055", lng="-1.39832", status="open", title="A problem", photo=False):
    return {"service_request_id": str(1000 + n), "service_name": service, "requested_datetime": when,
            "status": status, "title": title, "description": f"{title}: long text by the resident",
            "detail": "long text", "lat": lat, "long": lng,
            "media_url": "https://www.fixmystreet.com/photo/1.jpeg" if photo else ""}


FEED = [
    item(1, "Potholes", "2026-10-01T09:00:00+01:00", title="Pothole outside 31 Earls Road", photo=True),
    item(2, "Potholes", "2026-10-03T09:00:00+01:00", title="Same pothole again"),
    item(3, "Traffic lights", "2026-10-02T09:00:00+01:00", lat="50.92091", lng="-1.39860", status="closed"),
    item(4, "Noise nuisance", "2026-10-02T10:00:00+01:00", title="Loud music at number 4"),
    item(5, "Flytipping", "2026-10-04T09:00:00+01:00", lat="50.90000", lng="-1.40000", title="Alma 54"),
]
GEOCODE = {"50.92055,-1.39832": "Earls Road", "50.92091,-1.39860": "Avenue Road", "50.90000,-1.40000": ""}


class ImportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cache = Path(self.tmp.name) / "cache"
        cache.mkdir()
        (cache / "open311_recent.json").write_text(json.dumps({"service_requests": FEED}), encoding="utf-8")
        (cache / "geocode.json").write_text(json.dumps(GEOCODE), encoding="utf-8")
        for name, value in (("CACHE", cache), ("REPORTS_CACHE", cache / "open311_recent.json"),
                            ("GEOCODE_CACHE", cache / "geocode.json")):
            patch = unittest.mock.patch.object(fms, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        offline = unittest.mock.patch.object(fms.urllib.request, "urlopen",
                                             side_effect=AssertionError("no network in tests"))
        offline.start()
        self.addCleanup(offline.stop)
        self.path = Path(self.tmp.name) / "import.db"
        reports_db.init_db(self.path)
        self.conn = reports_db.connect(self.path)
        self.addCleanup(self.conn.close)
        self.counts = fms.import_reports(self.conn, fms.fetch_reports(), offline=True)

    def rows(self):
        return {r["source_url"].rsplit("/", 1)[1]: dict(r) for r in self.conn.execute("SELECT * FROM reports")}


class ImportTest(ImportCase):
    def test_categories_map_cleanly_or_go_to_unclear_other(self):
        rows = self.rows()
        self.assertEqual(rows["1001"]["category_id"], "pothole")
        self.assertEqual(rows["1003"]["category_id"], "unclear_other")
        self.assertEqual(rows["1005"]["category_id"], "fly_tipping")
        self.assertTrue(set(fms.CATEGORY_MAP.values()) <= set(tools.category_labels()))

    def test_a_report_about_a_home_is_not_imported(self):
        self.assertNotIn("1004", self.rows())
        self.assertEqual(self.counts["skipped_category"], 1)
        self.assertEqual(self.counts["imported"], 4)

    def test_status_open_is_new_and_closed_is_resolved(self):
        rows = self.rows()
        self.assertEqual(rows["1001"]["status"], "new")
        self.assertEqual(rows["1003"]["status"], "resolved")

    def test_the_duplicate_rule_links_a_later_open_report_on_the_same_street(self):
        rows = self.rows()
        self.assertIsNone(rows["1001"]["duplicate_of"])
        self.assertEqual(rows["1002"]["duplicate_of"], rows["1001"]["id"])

    def test_only_the_kept_fields_and_no_personal_data(self):
        rows = self.rows()
        first = rows["1001"]
        self.assertEqual(first["description"], "Pothole outside Earls Road")
        self.assertEqual(rows["1005"]["description"], "Alma")
        self.assertEqual((first["has_photo"], rows["1002"]["has_photo"]), (1, 0))
        self.assertIsNone(first["photo_guid"])
        self.assertIsNone(first["reporter_ref"])
        self.assertIsNone(first["severity"])
        self.assertEqual(first["source"], "fixmystreet")
        self.assertEqual(first["source_url"], "https://www.fixmystreet.com/report/1001")
        self.assertEqual(first["location"], "Earls Road")
        dump = json.dumps(list(rows.values()))
        for leaked in ("50.92055", "-1.39832", "long text by the resident"):
            self.assertNotIn(leaked, dump)

    def test_no_street_is_kept_empty_not_guessed(self):
        row = self.rows()["1005"]
        self.assertIsNone(row["location"])
        self.assertIsNone(row["duplicate_of"])

    def test_every_row_has_its_own_link_token(self):
        tokens = [r["link_token"] for r in self.rows().values()]
        self.assertEqual(len(set(tokens)), len(tokens))

    def test_running_again_adds_nothing(self):
        again = fms.import_reports(self.conn, fms.fetch_reports(), offline=True)
        self.assertEqual((again["imported"], again["already_present"]), (0, 4))

    def test_agent_reports_are_marked_agent(self):
        with unittest.mock.patch.object(tools._location_service, "forward_geocode", return_value=None):
            rid = tools.save_report("pothole", "Lawn Road", "Hole", conn=self.conn)["report_id"]
        row = self.conn.execute("SELECT source, source_url FROM reports WHERE id = ?", (rid,)).fetchone()
        self.assertEqual((row["source"], row["source_url"]), ("agent", None))


class PageTest(ImportCase):
    def setUp(self):
        super().setUp()
        self.client = website.create_app(self.path, "pw").test_client()

    def test_imported_rows_look_like_any_other_row(self):
        reports = self.client.get("/council/reports.json", headers=AUTH).get_json()["reports"]
        self.assertEqual(len(reports), 4)
        body = json.dumps(reports)
        for hidden in ('"source"', '"source_url"', "fixmystreet.com/report"):
            self.assertNotIn(hidden, body)
        self.assertTrue(all(r["link_token"] is None for r in reports))

    def test_no_resident_page_for_an_imported_report(self):
        token = self.rows()["1001"]["link_token"]
        self.assertEqual(self.client.get(f"/r/{token}").status_code, 404)

    def test_the_credit_is_in_the_council_footer_only(self):
        council = self.client.get("/council", headers=AUTH).get_data(as_text=True)
        self.assertIn('<footer class="credit wrap">Report data: mySociety FixMyStreet (ODC-BY)</footer>', council)
        self.assertNotIn("fixmystreet.com/report", council)
        self.assertNotIn("synthetic", council.lower())
        resident = self.client.get("/r/not-a-real-token").get_data(as_text=True)
        self.assertNotIn("FixMyStreet", resident)


class ResetTest(unittest.TestCase):
    def test_reset_without_a_cache_stops_before_deleting_anything(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(fms, "REPORTS_CACHE", Path(tmp) / "missing.json"), \
                unittest.mock.patch.object(sys, "argv", ["import_fixmystreet.py", "--reset"]), \
                unittest.mock.patch.object(reports_db, "DB_PATH", Path(tmp) / "keep.db"):
            (Path(tmp) / "keep.db").write_bytes(b"x")
            with self.assertRaises(SystemExit):
                fms.main()
            self.assertTrue((Path(tmp) / "keep.db").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
