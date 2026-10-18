"""Tests for the photo reference columns, the attach helpers and /r/<token>/photo.

Standard library plus Flask, no network: bb.download_attachment is patched, so
nothing here talks to BlueBubbles.

Run:
  python code/test_photos.py
"""

import sqlite3
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# photos must be imported before any app is created: it registers its route on
# website.site at import time, and a blueprint accepts new routes only before it
# is registered on an app.
import photos
import reports_db
import website

# The reports table as it was built before the photo columns, so the migration is
# tested against the real legacy shape rather than a copy of schema.sql.
LEGACY_SCHEMA = """
CREATE TABLE reports (
  id            TEXT PRIMARY KEY,
  created_at    TEXT NOT NULL,
  category_id   TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'new',
  severity      TEXT,
  location      TEXT,
  description   TEXT,
  has_photo     INTEGER NOT NULL DEFAULT 0,
  duplicate_of  TEXT,
  reporter_ref  TEXT,
  link_token    TEXT UNIQUE NOT NULL
);
"""

LEGACY_ROW = (
    "INSERT INTO reports (id, created_at, category_id, status, severity, location, "
    "description, has_photo, duplicate_of, reporter_ref, link_token) "
    "VALUES ('R-0001', '2026-09-30T08:00:00+00:00', 'pothole', 'new', 'high', "
    "'Weston Lane', 'Deep pothole', 1, NULL, 'h-legacy', 'legacytoken1234')"
)

GUID = "iMessage;-;at-0-1A2B3C4D-photo"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg bytes"
PNG = b"\x89PNG\r\n\x1a\n" + b"png bytes"


def columns(path):
    conn = sqlite3.connect(path)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(reports)")]
    finally:
        conn.close()


def legacy_db(path):
    """A populated database as it was built before photo_guid and photo_mime."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute(LEGACY_ROW)
        conn.commit()
    finally:
        conn.close()
    return path


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "legacy.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_adds_both_columns_to_an_existing_file(self):
        legacy_db(self.path)
        self.assertEqual(len(columns(self.path)), 11)
        self.assertEqual(reports_db.init_db(self.path), 1)
        self.assertIn("photo_guid", columns(self.path))
        self.assertIn("photo_mime", columns(self.path))

    def test_keeps_the_existing_rows(self):
        legacy_db(self.path)
        reports_db.init_db(self.path)
        conn = reports_db.connect(self.path)
        try:
            row = conn.execute(
                "SELECT location, has_photo, photo_guid, photo_mime FROM reports WHERE id = 'R-0001'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["location"], "Weston Lane")
        self.assertEqual(row["has_photo"], 1)   # the 36 legacy "says photo, has none" rows
        self.assertIsNone(row["photo_guid"])
        self.assertIsNone(row["photo_mime"])

    def test_running_twice_changes_nothing(self):
        legacy_db(self.path)
        reports_db.init_db(self.path)
        after_first = columns(self.path)
        self.assertEqual(reports_db.init_db(self.path), 1)
        self.assertEqual(columns(self.path), after_first)
        self.assertEqual(after_first.count("photo_guid"), 1)
        self.assertEqual(after_first.count("photo_mime"), 1)

    def test_a_fresh_file_gets_the_columns_from_the_schema(self):
        # A fresh file starts empty: real reports come from import_fixmystreet.py or the agent.
        count = reports_db.init_db(self.path)
        self.assertEqual(count, 0)
        self.assertIn("photo_guid", columns(self.path))
        self.assertIn("photo_mime", columns(self.path))

    def test_the_council_columns_exclude_the_attachment_guid(self):
        self.assertNotIn("photo_guid", reports_db.COUNCIL_COLUMNS)
        self.assertNotIn("photo_mime", reports_db.COUNCIL_COLUMNS)
        self.assertNotIn("reporter_ref", reports_db.COUNCIL_COLUMNS)
        self.assertIn("has_photo", reports_db.COUNCIL_COLUMNS)


class DbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "photos.db"
        reports_db.init_db(self.path)
        self.conn = reports_db.connect(self.path)
        self.next_id = 9001

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def add_report(self, **overrides):
        """Insert one report row, defaulting to an open, photo-less report."""
        report = {
            "id": f"R-{self.next_id:04d}",
            "created_at": "2026-10-17T09:00:00+00:00",
            "category_id": "pothole",
            "status": "new",
            "severity": "high",
            "location": "Weston Lane",
            "description": "Deep pothole",
            "has_photo": 0,
            "duplicate_of": None,
            "reporter_ref": "h-sender",
            "link_token": f"token{self.next_id:011d}",
        }
        self.next_id += 1
        report.update(overrides)
        self.conn.execute(
            "INSERT INTO reports (id, created_at, category_id, status, severity, location, "
            "description, has_photo, duplicate_of, reporter_ref, link_token) VALUES "
            "(:id, :created_at, :category_id, :status, :severity, :location, :description, "
            ":has_photo, :duplicate_of, :reporter_ref, :link_token)",
            report,
        )
        return report

    def row(self, report_id):
        return self.conn.execute(
            "SELECT has_photo, photo_guid, photo_mime FROM reports WHERE id = ?", (report_id,)
        ).fetchone()


class SetPhotoTest(DbCase):
    def test_attaches_the_first_photo_and_flags_has_photo(self):
        report = self.add_report()
        self.assertTrue(reports_db.set_photo(self.conn, report["id"], GUID, "image/jpeg"))
        row = self.row(report["id"])
        self.assertEqual(row["photo_guid"], GUID)
        self.assertEqual(row["photo_mime"], "image/jpeg")
        self.assertEqual(row["has_photo"], 1)

    def test_refuses_to_overwrite_a_photo_already_attached(self):
        report = self.add_report()
        self.assertTrue(reports_db.set_photo(self.conn, report["id"], GUID, "image/jpeg"))
        self.assertFalse(reports_db.set_photo(self.conn, report["id"], "second-guid", "image/png"))
        row = self.row(report["id"])
        self.assertEqual(row["photo_guid"], GUID)
        self.assertEqual(row["photo_mime"], "image/jpeg")

    def test_unknown_report_and_missing_values_attach_nothing(self):
        self.assertFalse(reports_db.set_photo(self.conn, "R-9999", GUID, "image/jpeg"))
        report = self.add_report()
        self.assertFalse(reports_db.set_photo(self.conn, report["id"], "", "image/jpeg"))
        self.assertIsNone(self.row(report["id"])["photo_guid"])


class OpenReportsForTest(DbCase):
    def test_returns_that_senders_open_report_without_a_photo(self):
        mine = self.add_report()
        self.add_report(reporter_ref="h-someone-else")
        found = reports_db.open_reports_for(self.conn, "h-sender")
        self.assertEqual([r["id"] for r in found], [mine["id"]])
        self.assertEqual(set(found[0]), {"id", "created_at", "category_id", "location", "link_token"})

    def test_skips_resolved_reports_and_ones_that_already_have_a_photo(self):
        resolved = self.add_report(status="resolved", created_at="2026-10-17T11:00:00+00:00")
        photoed = self.add_report(created_at="2026-10-17T10:00:00+00:00", has_photo=1)
        reports_db.set_photo(self.conn, photoed["id"], GUID, "image/jpeg")
        open_one = self.add_report(created_at="2026-10-17T09:00:00+00:00")
        found = reports_db.open_reports_for(self.conn, "h-sender")
        self.assertEqual([r["id"] for r in found], [open_one["id"]])
        self.assertNotIn(resolved["id"], [r["id"] for r in found])

    def test_newest_first_and_at_most_three(self):
        made = [self.add_report(created_at=f"2026-10-17T0{hour}:00:00+00:00") for hour in range(1, 6)]
        found = reports_db.open_reports_for(self.conn, "h-sender")
        self.assertEqual(len(found), 3)
        self.assertEqual([r["id"] for r in found], [r["id"] for r in reversed(made)][:3])

    def test_no_sender_returns_nothing(self):
        self.add_report()
        self.assertEqual(reports_db.open_reports_for(self.conn, None), [])
        self.assertEqual(reports_db.open_reports_for(self.conn, ""), [])


class PhotoRouteTest(DbCase):
    def setUp(self):
        super().setUp()
        self.app = website.create_app(self.path, "test-password")
        self.client = self.app.test_client()

    def with_photo(self, **overrides):
        report = self.add_report(**overrides)
        self.assertTrue(reports_db.set_photo(self.conn, report["id"], GUID, "image/jpeg"))
        return report

    def get(self, token, payload=(JPEG, "image/jpeg")):
        with unittest.mock.patch.object(photos.bb, "download_attachment",
                                        return_value=payload) as fetch:
            response = self.client.get(f"/r/{token}/photo")
        return response, fetch

    def test_serves_the_image_with_private_headers(self):
        report = self.with_photo()
        response, fetch = self.get(report["link_token"])
        fetch.assert_called_once_with(GUID, width=1024)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.get_data(), JPEG)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertIn("noindex", response.headers["X-Robots-Tag"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Content-Disposition"], "inline")
        self.assertNotIn("ETag", response.headers)

    def test_png_is_served_as_png(self):
        report = self.add_report()
        reports_db.set_photo(self.conn, report["id"], GUID, "image/png")
        response, _ = self.get(report["link_token"], payload=(PNG, "image/png"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")

    def test_an_unspecified_download_type_falls_back_to_the_stored_type(self):
        report = self.with_photo()   # stored image/jpeg
        response, _ = self.get(report["link_token"], payload=(JPEG, "application/octet-stream"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")

    def test_only_image_types_are_served(self):
        report = self.add_report()
        reports_db.set_photo(self.conn, report["id"], GUID, "application/pdf")
        response, _ = self.get(report["link_token"], payload=(b"%PDF-1.4", "application/pdf"))
        self.assertEqual(response.status_code, 404)

    def test_unknown_token_is_a_404(self):
        response, fetch = self.get("nosuchtoken1234")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(fetch.call_count, 0)
        self.assertIn("No photo", response.get_data(as_text=True))

    def test_a_token_that_is_not_token_shaped_is_a_404(self):
        for token in ("short", "x" * 200, "R-0001"):
            response, _ = self.get(token)
            self.assertEqual(response.status_code, 404, token)

    def test_a_report_with_no_photo_is_a_404(self):
        report = self.add_report()   # has_photo = 0, no guid
        response, fetch = self.get(report["link_token"])
        self.assertEqual(response.status_code, 404)
        self.assertEqual(fetch.call_count, 0)

    def test_a_legacy_has_photo_row_with_no_guid_is_a_404(self):
        report = self.add_report(has_photo=1)
        response, fetch = self.get(report["link_token"])
        self.assertEqual(response.status_code, 404)
        self.assertEqual(fetch.call_count, 0)

    def test_a_failed_download_is_a_404(self):
        report = self.with_photo()
        response, _ = self.get(report["link_token"], payload=None)
        self.assertEqual(response.status_code, 404)

    def test_the_guid_never_appears_in_a_response(self):
        report = self.with_photo()
        response, _ = self.get(report["link_token"])
        self.assertNotIn(GUID.encode(), response.get_data())
        self.assertNotIn(GUID, str(response.headers))
        self.assertNotIn(GUID, self.client.get(f"/r/{report['link_token']}").get_data(as_text=True))
        miss, _ = self.get("nosuchtoken1234")
        self.assertNotIn(GUID, miss.get_data(as_text=True))


class ResidentPhotoTest(DbCase):
    def setUp(self):
        super().setUp()
        self.app = website.create_app(self.path, "test-password")
        self.client = self.app.test_client()
        self._status = website.tools.get_report_status

    def status_with_photo_url(self, token, conn=None):
        """get_report_status as the resident page will see it: with photo_url, no guid.

        tools.get_report_status gains photo_url in its own change; until that lands
        this stands in for it, and steps aside once the real one reports the field.
        """
        report = self._status(token, conn=conn)
        if "photo_url" in report:
            return report
        row = conn.execute("SELECT photo_guid FROM reports WHERE link_token = ?",
                           (token,)).fetchone() if conn is not None else None
        report["photo_url"] = f"/r/{token}/photo" if row and row["photo_guid"] else None
        return report

    def page(self, token):
        with unittest.mock.patch.object(website.tools, "get_report_status",
                                        side_effect=self.status_with_photo_url):
            return self.client.get(f"/r/{token}").get_data(as_text=True)

    def test_a_report_with_a_photo_renders_the_image(self):
        report = self.add_report()
        reports_db.set_photo(self.conn, report["id"], GUID, "image/jpeg")
        html = self.page(report["link_token"])
        self.assertIn(f'src="/r/{report["link_token"]}/photo"', html)
        self.assertIn('alt="The photo you sent with your report"', html)
        self.assertIn('loading="lazy"', html)
        self.assertIn("max-width:100%;height:auto", html)
        self.assertIn(">Your photo</a>", html)
        self.assertNotIn(GUID, html)
        self.assertNotIn("<script", html)

    def test_a_legacy_row_says_a_photo_was_sent_and_shows_no_image(self):
        report = self.add_report(has_photo=1)
        html = self.page(report["link_token"])
        self.assertIn("You sent a photo", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("/photo", html)

    def test_a_report_without_a_photo_says_so(self):
        report = self.add_report()
        html = self.page(report["link_token"])
        self.assertIn("No photo", html)
        self.assertNotIn("<img", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
